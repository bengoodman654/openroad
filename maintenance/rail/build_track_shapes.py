#!/usr/bin/env python3
"""Track-aligned (not guaranteed train-path-exact) geometry from Network Rail's
Open Government Licence track centreline dataset, assembled off-host.

The original National Rail GTFS passing-point sketch remains the fallback.
No track graph or expensive pathfinding runs on shared cPanel hosting.
"""
import argparse,collections,heapq,json,math,sqlite3,time,zlib
import numpy as np
import shapefile
from pyproj import Transformer
from scipy.spatial import cKDTree

def build(index,links_path,deadline_seconds=220):
    started=time.monotonic()
    db=sqlite3.connect(index)
    db.execute("PRAGMA synchronous=OFF")
    db.execute("PRAGMA journal_mode=OFF")
    db.execute("PRAGMA cache_size=-20000")
    cols={r[1] for r in db.execute("PRAGMA table_info(rail_shapes)")}
    if "quality" not in cols:db.execute("ALTER TABLE rail_shapes ADD COLUMN quality TEXT NOT NULL DEFAULT 'schematic'")
    entries=[]
    for sid,blob in db.execute("SELECT shape_id,points FROM rail_shapes"):
        points=json.loads(zlib.decompress(blob))
        if len(points)>=2:entries.append((sid,points))
    if len(entries)<1000:raise ValueError("Not enough National Rail GTFS shapes")
    geodetic=Transformer.from_crs("EPSG:4326","EPSG:27700",always_xy=True)
    inverse=Transformer.from_crs("EPSG:27700","EPSG:4326",always_xy=True)
    reader=shapefile.Reader(links_path)
    links=[]
    for shape in reader.iterShapes():
        pts=shape.points
        if len(pts)<2:continue
        parts=list(shape.parts)+[len(pts)]
        for a,b in zip(parts,parts[1:]):
            if b-a<2:continue
            xy=np.asarray(pts[a:b],dtype=np.float64)
            if np.any(~np.isfinite(xy)):continue
            links.append(xy)
    if len(links)<20000:raise ValueError("Track centreline source is incomplete")
    endpoints=np.asarray([p for link in links for p in (link[0],link[-1])])
    parent=list(range(len(endpoints)))
    def find(i):
        while parent[i]!=i:
            parent[i]=parent[parent[i]];i=parent[i]
        return i
    def join(a,b):
        a=find(a);b=find(b)
        if a!=b:parent[max(a,b)]=min(a,b)
    tree=cKDTree(endpoints)
    for a,b in tree.query_pairs(4.5):join(a,b)
    endkeys={find(i):i for i in range(len(endpoints))}
    node_ids={root:i for i,root in enumerate(endkeys)}
    end_nodes=[node_ids[find(i)] for i in range(len(endpoints))]
    coords={node_ids[root]:tuple(endpoints[root]) for root in endkeys}
    next_node=len(coords)
    # All GTFS passing-point anchors are deduplicated before track snapping.
    anchors={}
    for sid,points in entries:
        for p in points:
            if not isinstance(p,list) or len(p)!=2:continue
            k=(round(float(p[0]),5),round(float(p[1]),5))
            if k not in anchors:anchors[k]=None
    keys=list(anchors)
    lon=[k[1] for k in keys];lat=[k[0] for k in keys]
    xs,ys=geodetic.transform(lon,lat)
    # Sample existing published track vertices. This is a fixed, off-host
    # preprocessing job, never a request-time nearest-geometry operation.
    verts=np.concatenate(links,axis=0)
    offset=np.zeros(len(links)+1,dtype=np.int64)
    for i,l in enumerate(links):offset[i+1]=offset[i]+len(l)
    vertexTree=cKDTree(verts)
    near,indices=vertexTree.query(np.column_stack((xs,ys)),k=5)
    insert=collections.defaultdict(set)
    anchor_members={}
    for k,distances,ids,x,y in zip(keys,near,indices,xs,ys):
        candidates=[]
        for d,idx in zip(np.atleast_1d(distances),np.atleast_1d(ids)):
            if float(d)>360:continue
            link=int(np.searchsorted(offset,int(idx),side="right")-1)
            vertex=int(idx-offset[link])
            if all(x[0]!=link for x in candidates):
                insert[link].add(vertex)
                candidates.append((link,vertex,float(d)))
            if len(candidates)>=2:break
        anchor_members[k]=(candidates,(float(x),float(y)))
    # Build an undirected physical track graph from surveyed link polylines.
    graph=collections.defaultdict(list);edgepaths={}
    def edge(u,v,track):
        if u==v or len(track)<2:return
        total=float(np.linalg.norm(np.diff(track,axis=0),axis=1).sum())
        if total<0.1:return
        length=total
        graph[u].append((v,length));graph[v].append((u,length))
        edgepaths[(u,v)]=track
        edgepaths[(v,u)]=track[::-1]
    link_nodes={}
    for i,track in enumerate(links):
        inner=sorted({0,len(track)-1}|insert.get(i,set()))
        members=[]
        for v in inner:
            if v==0:n=end_nodes[2*i]
            elif v==len(track)-1:n=end_nodes[2*i+1]
            else:
                n=next_node;next_node+=1;coords[n]=tuple(track[v])
            members.append((v,n))
            link_nodes[(i,v)]=n
        for (vi,ni),(vj,nj) in zip(members,members[1:]):
            edge(ni,nj,track[vi:vj+1])
    anchor_nodes={}
    for k,(candidates,xy) in anchor_members.items():
        if not candidates:continue
        n=next_node;next_node+=1;coords[n]=xy
        for link,vertex,d in candidates:
            tracknode=link_nodes[(link,vertex)]
            # The route line must join the actual platform location and track.
            # Prefer the nearest track without attaching remote railway links.
            edge(n,tracknode,np.asarray([xy,coords[tracknode]]))
        anchor_nodes[k]=n
    # A* using metric XY distance. All routing remains on physical track edges.
    cache={}
    def path(a,b):
        nonlocal started
        if a==b:return [a]
        key=(a,b)
        if key in cache:return cache[key]
        goal=coords[b]
        heuristic=lambda n:math.hypot(coords[n][0]-goal[0],coords[n][1]-goal[1])
        frontier=[(heuristic(a),0,a)]
        costs={a:0};previous={}
        visited=0
        while frontier:
            _,g,u=heapq.heappop(frontier)
            if g>costs[u]+0.001:continue
            if u==b:break
            visited+=1
            if visited>13000:cache[key]=None;return None
            for v,w in graph[u]:
                cost=g+w
                if cost>=costs.get(v,float("inf")):continue
                costs[v]=cost;previous[v]=u
                heapq.heappush(frontier,(cost+heuristic(v),cost,v))
        if b not in previous:cache[key]=None;return None
        found=[b]
        while found[-1]!=a:
            found.append(previous[found[-1]])
        found.reverse()
        cache[key]=found
        cache[(b,a)]=found[::-1]
        return found
    def collect(route):
        seq=[]
        for u,v in zip(route,route[1:]):
            segment=edgepaths.get((u,v))
            if segment is None:return None
            seq.extend(segment if not seq else segment[1:])
        return seq
    written=aligned=partial=0
    for si,(sid,points) in enumerate(entries):
        if si%120==0 and time.monotonic()-started>deadline_seconds:break
        route=[];matched=0;segments=0
        for p,q in zip(points,points[1:]):
            a=(round(float(p[0]),5),round(float(p[1]),5))
            b=(round(float(q[0]),5),round(float(q[1]),5))
            segments+=1
            aa=anchor_nodes.get(a);bb=anchor_nodes.get(b)
            visited=path(aa,bb) if aa is not None and bb is not None else None
            dx=(anchor_members[a][1][0]-anchor_members[b][1][0])
            dy=(anchor_members[a][1][1]-anchor_members[b][1][1])
            direct=math.hypot(dx,dy)
            track=collect(visited) if visited else None
            length=float(np.linalg.norm(np.diff(np.asarray(track),axis=0),axis=1).sum()) if track and len(track)>1 else float("inf")
            if track and length<=max(500,direct*2.4+3500):
                matched+=1
                route.extend(track if not route else track[1:])
            else:
                # Refuse absurd detours and disconnected tracks. Use the
                # original GTFS station-to-station line for this section.
                xy=np.asarray([anchor_members[a][1],anchor_members[b][1]])
                route.extend(xy if not route else xy[1:])
        if not route or matched<1:continue
        line=np.asarray(route,dtype=np.float64)
        if len(line)>2:
            # Ramer–Douglas–Peucker in metres preserves track curvature while
            # substantially reducing storage on the owner's shared server.
            from shapely.geometry import LineString
            geom=LineString(line).simplify(13,preserve_topology=False)
            line=np.asarray(geom.coords)
        if len(line)>2200:
            ix=np.round(np.linspace(0,len(line)-1,2200)).astype(int);line=line[ix]
        longitude,latitude=inverse.transform(line[:,0].tolist(),line[:,1].tolist())
        output=[[round(float(lat),5),round(float(lon),5)] for lat,lon in zip(latitude,longitude)]
        quality="track-aligned" if matched==segments else "partly-track-aligned"
        blob=zlib.compress(json.dumps(output,separators=(",",":")).encode(),8)
        db.execute("UPDATE rail_shapes SET points=?,quality=? WHERE shape_id=?",(blob,quality,sid))
        written+=1
        if quality=="track-aligned":aligned+=1
        else:partial+=1
        if si%100==0:db.commit()
    db.commit()
    coverage=written/len(entries)
    print("RAIL_TRACK_ALIGNMENT total=%d written=%d fully=%d partial=%d coverage=%.3f sec=%d" %
          (len(entries),written,aligned,partial,coverage,time.monotonic()-started),flush=True)
    if coverage<.12:raise ValueError("Track-alignment coverage too low: refuse source")
    return dict(total=len(entries),written=written,fully=aligned,partial=partial)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("sqlite");p.add_argument("shapefile")
    p.add_argument("--deadline",type=int,default=220)
    opts=p.parse_args()
    build(opts.sqlite,opts.shapefile,opts.deadline)
