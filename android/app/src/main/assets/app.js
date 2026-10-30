(() => {
  const el = id => document.getElementById(id);
  let map, userMarker, destMarker;
  let current = null, mode = 'drive', destination = null, destinationLabel = '', destinationAddress = '', destinationMeta = null, originOverride = null;
  let routeResponse = null, selectedRoute = 0, selectedRouteId = '', routeSelectionUserMade = false, routeLayerIds = [], routeLabelMarkers = [];
  let transitStopData = new Map(), transitOverlaySignature = '', pendingTransitOverlayRefresh = false;
  let navigating = false, trafficVisible = true, mapLoaded = false;
  let poiVisible = true, cycleLayerVisible = false;
  const poiLayerDefaults = new Map();
  let nativeReadySignalled = false, initialLocationCentred = false;
  let navigationFollow = true, angledView = false;
  let pendingDirections = false, locating = false;
  // Independent UI watchdog: also works if the native callback is delayed or never arrives.
  let transitSearchTimer = 0, transitSearchRequest = 0;
  let home = null;
  let ttsChoice = {engine:'', voice:''}, ttsEngines = [];
  let longPressTimer = null, longPressStartPoint = null, longPressStartLngLat = null;
  let searchRequestId = 0, suggestionRequestId = 0, mapAreaSearchRequestId = 0, homeSearchRequestId = 0, routeRequestId = 0, alongRouteRequestId = 0;
  let searchDebounce = null, areaSearchMarkers = [], starredMarkers = [], alongRouteMarkers = [], busRouteMarkers = [], busLiveMarkers = [];
  let busRouteLayerIds = [], busRouteStopData = new Map(), busRouteRequestId = 0, busLiveRequestId = 0, busStopRequestId = 0, transitPreloadAreaRequestId = 0, tomTomRevealed = false;
  let alongRouteLayoutFrame = 0;
  let contactsEnabled = false;
  let railBoardContext = null;
  const lastRailBoardLookup = new Map();
  const trainDetailsCache=new Map(),trainDetailsPending=new Map(),trainLiveCache=new Map(),trainLivePending=new Map();
  let trainRequestSeq=0,expandedTrainTimetable='';
  const trainKey=leg=>[leg?.railTripId,leg?.fromCrs,leg?.toCrs,leg?.departureEpoch].join(':');
  const isIndexedTrain=leg=>Number.isInteger(Number(leg?.railTripId))&&Number(leg.railTripId)>0&&
    /^[A-Z]{3}$/.test(String(leg?.fromCrs||''))&&/^[A-Z]{3}$/.test(String(leg?.toCrs||''))&&
    Number(leg?.departureEpoch)>1600000000;

  function applyTrainDetailsFromCache(route){
    if(!route?.transitLegs||!route?.legs)return;
    route.transitLegs.forEach((leg,li)=>{
      if(!isIndexedTrain(leg))return;
      const key=trainKey(leg),detail=trainDetailsCache.get(key),live=trainLiveCache.get(key);
      if(detail?.ok){
        leg.railTimetable=detail.calls;
        leg.railHeadSign=detail.headsign||'';
        leg.railGeometryNote=detail.geometryMessage||'';
        if(Array.isArray(detail.routePoints)&&detail.routePoints.length>=2){
          const geom=route.legs[li];
          if(geom)geom.points=detail.routePoints;
          leg.geometryStatus='schematic';
        }else leg.geometryStatus='stations_only';
      }
      if(live?.matched===true){
        leg.platform=live.platform||'';
        leg.cancelled=live.cancelled===true;
        leg.liveDeparture=leg.cancelled?'Cancelled':(live.expected||leg.departure);
        leg.timeStatus='live';
        leg.liveNote=live.message||'Live information checked';
        leg.railLiveCheckedAt=live.checkedAt||'';
        route.clearRouteDataStatus='mixed';
      }else if(live?.status){leg.liveNote=live.message||'Live data unavailable';}
    });
  }
  function requestSelectedTrainDetails(routeIndex,onlyLeg=null){
    const route=routeResponse?.routes?.[routeIndex];if(!route)return;
    route.transitLegs?.forEach((leg,i)=>{
      if(onlyLeg!==null&&i!==onlyLeg)return;
      if(!isIndexedTrain(leg))return;
      const key=trainKey(leg);
      if(!trainDetailsCache.has(key)&&![...trainDetailsPending.values()].some(v=>v.key===key)){
        const id=++trainRequestSeq;trainDetailsPending.set(id,{key});
        native()?.requestTrainTimetable?.(id,Number(leg.railTripId),leg.fromCrs,leg.toCrs,Number(leg.departureEpoch));
      }else if(trainDetailsCache.has(key))requestSelectedTrainLive(leg);
    });
  }
  function requestSelectedTrainLive(leg,force=false){
    if(!isIndexedTrain(leg))return;
    const key=trainKey(leg);
    if(!force&&(trainLiveCache.has(key)||[...trainLivePending.values()].some(x=>x.key===key)))return;
    if([...trainLivePending.values()].some(x=>x.key===key))return;
    const id=++trainRequestSeq;trainLivePending.set(id,{key});
    native()?.requestTrainLive?.(id,leg.fromCrs,leg.toCrs,Number(leg.departureEpoch),
      String(trainDetailsCache.get(key)?.headsign||''));
  }
  function showTrainTimetableList(host,leg){
    const info=trainDetailsCache.get(trainKey(leg));
    const list=document.createElement('div');list.className='rail-timetable-list';
    if(!info?.ok){
      list.textContent=info?.failed?'Full train timetable unavailable.':'Loading scheduled calling points…';
      if(!info?.failed){const spin=document.createElement('span');spin.className='rail-inline-spinner';list.prepend(spin);}
      host.appendChild(list);return;
    }
    const caption=document.createElement('div');caption.className='rail-timetable-caption';
    caption.textContent='This train’s scheduled calls · '+(info.headsign||'National Rail')+
      ' · Platforms and delays are only shown when reliably matched with live Rail Data.';
    list.appendChild(caption);
    (info.calls||[]).forEach(call=>{
      const item=document.createElement('div');item.className='rail-timetable-stop'+
       (call.boarding?' boarding':'')+(call.alighting?' alighting':'')+
       (!call.withinJourney?' outside-journey':'');
      const name=document.createElement('strong');name.textContent=call.name||call.crs;
      const time=document.createElement('span');time.textContent=(call.scheduledArrival||call.scheduledDeparture||'—')+
          (call.boarding?' · Board':call.alighting?' · Alight':'');
      item.append(name,time);list.appendChild(item);
    });
    const disclaimer=document.createElement('small');disclaimer.textContent='Scheduled times for this service day; other platforms and delays cannot be verified from a departure board.';
    list.appendChild(disclaimer);host.appendChild(list);
  }


  let savedReturnToSettings = false;
  let transitPreference = 'balanced', transitViaStops = [], pendingTransitStop = false, pendingOriginSelection = false, pendingDestinationSelection = false, pendingViaEditIndex = -1;
  const TRANSIT_RESULT_LIMIT = 3;
  let routePlanningActive = false, transitNavigation = null;
  let viaDragState = null, settingsCurrentPage = 'home', transitPrefsReturnToSettings = false;
  let transitPreferences = {modes:{bus:true,coach:true,train:true,tube:true,tram:true,ferry:true,cablecar:true},walkSpeed:'normal',transferBuffer:'normal',accessibility:'none',transportApiFallback:false};
  let busServiceData = null, busServiceTab = 'timetable', busServiceReturnSheet = 'routeCard', busServiceTargetStop = null, busStopData = null, busStopReturnSheet = 'routeCard';
  let placeCategories={starred:true,contacts:false,pubs:false,restaurants:false,cafes:false,bakeries:false,takeaways:false,supermarkets:false,shopping:false,atms:false,postoffices:false,pharmacies:false,petrol:false,evcharging:false,parking:false,railstations:false,busstops:false,toilets:false,hospitals:false,hotels:false,parks:false,playgrounds:false,gyms:false,libraries:false,cinemas:false}, placeCategoryMarkers=new Map(), placeCategoryRequests=new Map(), placeCategoryRequestSeq=0, contactPlaceCache=[], contactBackgroundGeocodes=new Set();
  const TRANSIT_COLORS={foot:'#188b46',bus:'#e53935',coach:'#b73535',train:'#1d4f91',tube:'#7247d8',underground:'#7247d8',metro:'#7247d8',tram:'#ef7d00','light-rail':'#ef7d00',ferry:'#1597ad',cablecar:'#8a5a22','cable-car':'#8a5a22'};
  const TRANSIT_ALT_COLORS={foot:'#9fcfb0',bus:'#edaaa7',coach:'#d9aaa8',train:'#9fb2cb',tube:'#c5b8e8',underground:'#c5b8e8',metro:'#c5b8e8',tram:'#efc18b','light-rail':'#efc18b',ferry:'#9bc9d0',cablecar:'#cdb99d','cable-car':'#cdb99d'};
  const PLACE_CATEGORY_META={pubs:{query:'pub bar',symbol:'🍺',label:'Pub / bar'},restaurants:{query:'restaurant',symbol:'🍽',label:'Restaurant'},cafes:{query:'cafe',symbol:'☕',label:'Café'},bakeries:{query:'bakery',symbol:'🥖',label:'Bakery'},takeaways:{query:'takeaway fast food',symbol:'🥡',label:'Takeaway'},supermarkets:{query:'supermarket',symbol:'🛒',label:'Supermarket'},shopping:{query:'shopping centre mall',symbol:'🛍',label:'Shopping centre'},atms:{query:'atm cash machine',symbol:'🏧',label:'Cash machine'},postoffices:{query:'post office',symbol:'📮',label:'Post office'},pharmacies:{query:'pharmacy chemist',symbol:'💊',label:'Pharmacy'},petrol:{query:'petrol station',symbol:'⛽',label:'Petrol station'},evcharging:{query:'electric vehicle charging station',symbol:'🔌',label:'EV charging'},parking:{query:'car park parking',symbol:'🅿',label:'Parking'},railstations:{query:'railway station train station',symbol:'🚉',label:'Railway station'},busstops:{query:'bus stop',symbol:'🚏',label:'Bus stop'},toilets:{query:'public toilet',symbol:'🚻',label:'Public toilet'},hospitals:{query:'hospital',symbol:'🏥',label:'Hospital'},hotels:{query:'hotel',symbol:'🛏',label:'Hotel'},parks:{query:'park',symbol:'🌳',label:'Park'},playgrounds:{query:'playground',symbol:'🛝',label:'Playground'},gyms:{query:'gym fitness centre',symbol:'🏋',label:'Gym'},libraries:{query:'library',symbol:'📚',label:'Library'},cinemas:{query:'cinema movie theatre',symbol:'🎬',label:'Cinema'}};
  let placeRefreshTimer=0;

  function native() { return window.ClearRouteBridge; }
  function show(id, yes=true) { const node=el(id); if(node) node.classList.toggle('hidden', !yes); }
  function updateNetworkBanner(){const b=el('networkBanner');if(!b)return;const online=navigator.onLine!==false;b.classList.toggle('hidden',online);b.textContent=online?'':'No internet — current route remains available where cached';}
  window.addEventListener('online',updateNetworkBanner);window.addEventListener('offline',updateNetworkBanner);
  function toast(message) { el('toast').textContent = message; show('toast'); setTimeout(() => show('toast', false), 4200); }
  function formatDistance(m) { if(!Number.isFinite(m)) return '—'; if(m<10) return 'Now'; return m < 950 ? `${Math.max(10,Math.round(m/10)*10)} m` : `${(m/1000).toFixed(1)} km`; }
  function formatTime(seconds) { if(!Number.isFinite(seconds)||seconds<=0)return '—'; const m=Math.max(1,Math.round(seconds/60)); return m<60?`${m} min`:`${Math.floor(m/60)} hr ${m%60} min`; }
  function formatArrivalTime(seconds) { if(!Number.isFinite(seconds)||seconds<=0)return '—'; return new Date(Date.now()+seconds*1000).toLocaleTimeString('en-GB',{hour:'2-digit',minute:'2-digit'}); }
  function routeSummary(route) { const s=route?.summary||{}; return `${formatTime(Number(s.travelTimeInSeconds)||0)} • ${formatDistance(Number(s.lengthInMeters)||0)}`; }


  function normaliseTransitMode(mode){
    const m=String(mode||'').toLowerCase().replace(/_/g,'-');
    if(['walk','walking','foot'].includes(m))return 'foot';
    if(['national-rail','rail','overground'].includes(m))return 'train';
    if(['subway','underground','metro','dlr'].includes(m))return 'tube';
    if(['light-rail','light rail'].includes(m))return 'tram';
    if(['river','river-bus'].includes(m))return 'ferry';
    if(['public-bus'].includes(m))return 'bus';
    if(['cable-car','cable car'].includes(m))return 'cablecar';
    return m||'transit';
  }
  function transitModeColour(mode,selected=true){const key=normaliseTransitMode(mode);return (selected?TRANSIT_COLORS:TRANSIT_ALT_COLORS)[key]||(selected?'#546e7a':'#c3c9cd');}
  // Different vehicles within one selected journey must not appear as a single
  // continuous bus route. Keep the palette stable across the map and cards.
  const BUS_LEG_COLOURS=['#c62828','#1565c0','#00796b','#7b1fa2','#ad4e00','#455a64'];
  function transitLegColour(route,index,selected=true){
    const legs=route?.transitLegs||[],mode=normaliseTransitMode(legs[index]?.mode);
    if(!selected||!['bus','coach'].includes(mode))return transitModeColour(mode,selected);
    let ordinal=0;for(let i=0;i<index;i++)if(['bus','coach'].includes(normaliseTransitMode(legs[i]?.mode)))ordinal++;
    return BUS_LEG_COLOURS[ordinal%BUS_LEG_COLOURS.length];
  }
  function stopTravelBearing(stops,index){
    const a=stops[index],b=stops[index+1]||stops[index-1];
    if(!a||!b)return null;
    const al=Number(a.lat),an=Number(a.lon),bl=Number(b.lat),bn=Number(b.lon);
    if(![al,an,bl,bn].every(Number.isFinite))return null;
    if(Math.abs(al-bl)+Math.abs(an-bn)<1e-8)return null;
    return stops[index+1]?bearingTo(al,an,bl,bn):bearingTo(bl,bn,al,an);
  }
  function addStopDirectionIcon(){
    const id='openroad-stop-direction-v1';if(map.hasImage(id))return id;
    const canvas=document.createElement('canvas');canvas.width=36;canvas.height=36;
    const ctx=canvas.getContext('2d');if(!ctx)return null;
    ctx.beginPath();ctx.moveTo(18,3);ctx.lineTo(29,29);ctx.lineTo(18,24);ctx.lineTo(7,29);ctx.closePath();
    ctx.fillStyle='#fff';ctx.fill();ctx.lineWidth=2.5;ctx.strokeStyle='#25323d';ctx.stroke();
    map.addImage(id,ctx.getImageData(0,0,36,36),{pixelRatio:2});return id;
  }
  function transitModeIcon(mode){const key=normaliseTransitMode(mode);return key==='foot'?'🚶':key==='bus'?'🚌':key==='coach'?'🚍':key==='train'?'🚆':key==='tube'?'Ⓜ':key==='tram'?'🚊':key==='ferry'?'⛴':'●';}
  function transitModeLabel(mode){const key=normaliseTransitMode(mode);return key==='foot'?'Walk':key==='bus'?'Bus':key==='coach'?'Coach':key==='train'?'Train':key==='tube'?'Underground':key==='tram'?'Tram':key==='ferry'?'Ferry':key==='cablecar'?'Cable car':(mode||'Service');}
  function parseClockMinutes(v){if(!v||!/^\d{1,2}:\d{2}/.test(v))return null;const [h,m]=v.split(':').map(Number);return h*60+m;}
  function transitLegMinutes(leg){
    const explicit=Number(leg?.durationSeconds);if(Number.isFinite(explicit)&&explicit>0)return Math.max(1,Math.round(explicit/60));
    const d=String(leg?.duration||'');const match=d.match(/^(?:(\d+):)?(\d{1,2}):(\d{2})$/);if(match)return Number(match[1]||0)*60+Number(match[2])+Math.round(Number(match[3]||0)/60);
    const a=parseClockMinutes(leg?.departure),b=parseClockMinutes(leg?.arrival);if(a!=null&&b!=null)return Math.max(1,(b-a+1440)%1440);return null;
  }
  function transitChanges(route){const legs=(route?.transitLegs||[]).filter(x=>normaliseTransitMode(x.mode)!=='foot');return Math.max(0,legs.length-1);}
  function transitLoadingText(route){
    const legs=Array.isArray(route?.transitLegs)?route.transitLegs:[], pending=[];
    if(routeResponse?.clearRouteRefining)pending.push('better alternatives');
    if(legs.some(l=>normaliseTransitMode(l.mode)==='foot'&&l.geometryStatus==='loading'))pending.push('walking path');
    if(legs.some(l=>['bus','coach'].includes(normaliseTransitMode(l.mode))&&l.geometryStatus==='loading'))pending.push('bus path');
    if(route?.clearRouteLiveStatus==='loading')pending.push('live data');
    if(pending.length)return `Loading ${pending.join(' · ')}…`;
    const approx=[];
    if(legs.some(l=>normaliseTransitMode(l.mode)==='foot'&&l.geometryStatus==='fallback'))approx.push('walking path');
    if(legs.some(l=>['bus','coach'].includes(normaliseTransitMode(l.mode))&&l.geometryStatus==='fallback'))approx.push('bus path');
    return approx.length?`Approx. ${approx.join(' · ')}`:'';
  }
  function routeAllowedByTransitSettings(route){
    if(route?.clearRouteFeasible===false)return false;
    const modes=transitPreferences.modes||{},legs=route?.transitLegs||[];
    return legs.every(leg=>{const m=normaliseTransitMode(leg.mode);if(m==='foot')return true;return modes[m]!==false;});
  }
  function routeTravelSeconds(route){ return Math.max(1,Number(route?.summary?.travelTimeInSeconds)||1e9); }
  function transitDisplayIndices(){
    const routes=routeResponse?.routes||[];let ids=routes.map((_,i)=>i).filter(i=>routeAllowedByTransitSettings(routes[i]));
    const now=new Date(),nowMin=now.getHours()*60+now.getMinutes()+now.getSeconds()/60;
    const score=i=>{const r=routes[i],arr=parseClockMinutes(r?.clearRouteArrival),arrivalSecs=arr==null?routeTravelSeconds(r):(((arr-nowMin+1440)%1440)*60),changes=transitChanges(r),walkSecs=(r?.transitLegs||[]).filter(l=>normaliseTransitMode(l.mode)==='foot').reduce((sum,l)=>sum+(Number(l?.durationSeconds)||0),0),changePenalty=transitPreferences.transferBuffer==='cautious'?12*60:8*60;if(transitPreference==='quickest')return arrivalSecs+walkSecs*.02;if(transitPreference==='changes')return changes*1e7+arrivalSecs+walkSecs*.35;return arrivalSecs+changes*changePenalty+walkSecs*.80;};
    ids.sort((a,b)=>score(a)-score(b));
    return ids.slice(0,TRANSIT_RESULT_LIMIT);
  }
  function standardDisplayIndices(){
    const routes=routeResponse?.routes||[];if(!routes.length)return [];
    const bestSecs=Math.max(1,Number(routes[0]?.summary?.travelTimeInSeconds)||1),bestDist=Math.max(1,Number(routes[0]?.summary?.lengthInMeters)||1);
    let ids=routes.map((_,i)=>i).filter((i,pos)=>{if(pos===0)return true;const r=routes[i],secs=Math.max(1,Number(r?.summary?.travelTimeInSeconds)||1e9),dist=Math.max(1,Number(r?.summary?.lengthInMeters)||1e9);return secs<=bestSecs+Math.max(5*60,bestSecs*.30)&&dist<=bestDist*1.65+1000;}).slice(0,3);
    if(routeSelectionUserMade&&routes[selectedRoute]&&!ids.includes(selectedRoute))ids.push(selectedRoute);
    return ids;
  }
  function visibleRouteIndices(){ return mode==='transit'?transitDisplayIndices():standardDisplayIndices(); }

  function routeOrigin(){
    if(originOverride)return {lat:Number(originOverride.lat),lon:Number(originOverride.lon),name:originOverride.name||'Start location',address:originOverride.address||'',custom:true};
    if(current)return {lat:Number(current.lat),lon:Number(current.lon),name:'My location',address:'',custom:false};
    return null;
  }
  function routePointSelectionActive(){return pendingTransitStop||pendingOriginSelection||pendingDestinationSelection||pendingViaEditIndex>=0;}
  function resetRoutePointSelection(){pendingTransitStop=false;pendingOriginSelection=false;pendingDestinationSelection=false;pendingViaEditIndex=-1;const input=el('searchInput');if(input){input.readOnly=routePlanningActive;input.placeholder=routePlanningActive?'Destination':'Where to?';input.value=routePlanningActive?(destinationLabel||'Destination'):'';}}
  function beginRoutePointSearch(type,index=-1){
    pendingTransitStop=type==='add';pendingOriginSelection=type==='origin';pendingDestinationSelection=type==='destination';pendingViaEditIndex=type==='via'?index:-1;
    cancelActiveRouteRequest(false);closeRoutePlanner();const input=el('searchInput');input.readOnly=false;input.value='';input.placeholder=type==='origin'?'Start location':type==='destination'?'Destination':type==='via'?'Replace stop':'Add stop';input.focus();hideStarMenu();
    toast(type==='origin'?'Search for a new start location.':type==='destination'?'Search for a new destination.':type==='via'?'Search for a replacement stop.':'Search for the stop or place to add.');
  }
  function finishRoutePointSearch(){resetRoutePointSelection();hideSearchDropdown();clearAreaSearchMarkers();renderRoutePlanner();}
  function cancelRoutePointSearch(){const hadSelection=routePointSelectionActive();finishRoutePointSearch();finishRouteCalculationUi();if(hadSelection&&destination&&routeOrigin()&&routePlanningActive&&!routeResponse)calculateRoute();}
  function isCoordinateText(value){return /^-?\d{1,3}\.\d{3,}\s*,\s*-?\d{1,3}\.\d{3,}$/.test(String(value||'').trim());}
  function routePointName(name,address){const clean=String(name||'').trim();return /^(?:dropped\s+)?pin$/i.test(clean)?'Pin':(clean||'Place');}
  function routePlannerPoints(){
    const points=[],origin=routeOrigin();
    if(origin)points.push({lat:Number(origin.lat),lon:Number(origin.lon),name:origin.name||'My location',address:origin.address||'',meta:originOverride?.meta||null,source:origin.custom?(originOverride?.source||'custom'):'current'});
    transitViaStops.forEach(stop=>points.push({lat:Number(stop.lat),lon:Number(stop.lon),name:routePointName(stop.name,stop.address),address:stop.address||'',meta:stop.meta||null,source:stop.source||'via'}));
    if(destination)points.push({lat:Number(destination.lat),lon:Number(destination.lon),name:routePointName(destinationLabel,destinationAddress),address:destinationAddress||'',meta:destinationMeta||null,source:destinationMeta?.routePointSource||'destination'});
    return points;
  }
  function applyRoutePointOrder(points){
    if(!Array.isArray(points)||points.length<2)return;
    cancelActiveRouteRequest(false);
    const first=points[0],last=points[points.length-1],middle=points.slice(1,-1);
    if(first.source==='current'){originOverride=null;}else originOverride={lat:Number(first.lat),lon:Number(first.lon),name:first.name||'Start location',address:first.address||'',meta:first.meta||null,source:first.source||'custom'};
    transitViaStops=middle.map(p=>({lat:Number(p.lat),lon:Number(p.lon),name:p.name||'Stop',address:p.address||'',meta:p.meta||null,source:p.source||'via'}));
    destination={lat:Number(last.lat),lon:Number(last.lon)};destinationLabel=last.name||'Destination';destinationAddress=last.address||'';destinationMeta={...(last.meta||{}),routePointSource:last.source||'destination'};
    routeResponse=null;selectedRoute=0;selectedRouteId='';routeSelectionUserMade=false;clearRouteLayers();renderDestinationMarker();
    el('selectedDestinationName').textContent=destinationLabel;el('selectedDestinationAddress').textContent=destinationAddress;renderDestinationMeta();updateStarButton();el('destinationName').textContent=destinationLabel;
    setRoutePlanningActive(true);renderRoutePlanner();native()?.prepareTransitDestination?.(Number(destination.lat),Number(destination.lon));calculateRoute();
  }
  function commitRoutePointReorder(from,to){
    const points=routePlannerPoints();if(!Number.isInteger(from)||!Number.isInteger(to)||from===to||from<0||to<0||from>=points.length||to>=points.length)return;
    const [moved]=points.splice(from,1);points.splice(to,0,moved);applyRoutePointOrder(points);
  }
  function plannerPointDetail(point,isLast){
    const address=String(point?.address||'').trim();
    // Keep the route-point list deliberately terse. A dropped pin is the one case where
    // the otherwise anonymous destination needs a useful secondary label.
    return isLast&&point?.name==='Pin'&&isCoordinateText(address)?address:'';
  }
  function renderTransitPlanner(){
    const list=el('routePointList');if(!list)return;list.textContent='';const points=routePlannerPoints();
    points.forEach((point,i)=>{
      const isFirst=i===0,isLast=i===points.length-1,row=document.createElement('div');row.className='planner-route-point-row';row.dataset.index=String(i);
      const node=document.createElement('span');node.className='planner-route-node '+(isFirst?'origin':isLast?'destination':'via');node.setAttribute('aria-hidden','true');
      const main=document.createElement('button');main.type='button';main.className='planner-route-point-main';main.setAttribute('aria-label',`Change ${point.name||'route point'}`);
      const copy=document.createElement('span');copy.className='planner-route-point-copy';const name=document.createElement('span');name.className='planner-route-point-name';name.textContent=point.name||'Place';copy.appendChild(name);
      const detail=plannerPointDetail(point,isLast);if(detail){const small=document.createElement('small');small.textContent=detail;copy.appendChild(small);}main.appendChild(copy);
      main.onclick=()=>beginRoutePointSearch(isFirst?'origin':isLast?'destination':'via',isFirst||isLast?-1:i-1);
      const drag=document.createElement('button');drag.type='button';drag.className='planner-route-point-drag';drag.textContent='≡';drag.setAttribute('aria-label',`Reorder ${point.name||'route point'}`);
      drag.onpointerdown=e=>{if(points.length<2)return;viaDragState={from:i,target:i,pointerId:e.pointerId};try{drag.setPointerCapture(e.pointerId);}catch(_){}row.classList.add('dragging');e.preventDefault();e.stopPropagation();};
      drag.onpointermove=e=>{if(!viaDragState||viaDragState.pointerId!==e.pointerId)return;const target=document.elementFromPoint(e.clientX,e.clientY)?.closest?.('.planner-route-point-row');document.querySelectorAll('.planner-route-point-row.drag-target').forEach(n=>n.classList.remove('drag-target'));if(target){const idx=Number(target.dataset.index);if(Number.isInteger(idx)){viaDragState.target=idx;target.classList.add('drag-target');}}};
      const finish=e=>{if(!viaDragState||viaDragState.pointerId!==e.pointerId)return;const {from,target}=viaDragState;viaDragState=null;document.querySelectorAll('.planner-route-point-row').forEach(n=>n.classList.remove('dragging','drag-target'));commitRoutePointReorder(from,target);e.preventDefault();e.stopPropagation();};drag.onpointerup=finish;drag.onpointercancel=finish;
      row.append(node,main,drag);
      if(!isFirst&&!isLast){const remove=document.createElement('button');remove.type='button';remove.className='planner-route-point-remove';remove.textContent='×';remove.setAttribute('aria-label',`Remove ${point.name||'stop'}`);remove.onclick=e=>{e.stopPropagation();cancelActiveRouteRequest(false);transitViaStops.splice(i-1,1);renderRoutePlanner();if(destination&&routeOrigin())calculateRoute();};row.appendChild(remove);}
      list.appendChild(row);
    });
    const origin=routeOrigin();const from=el('routeCard')?.querySelector('.route-from');if(from)from.textContent=origin?.name||'My location';
  }
  function beginAddTransitStop(){const limit=mode==='drive'||mode==='transit'?6:1;if(transitViaStops.length>=limit)return toast('This travel mode supports up to '+limit+' intermediate stop'+(limit===1?'':'s')+'.');beginRoutePointSearch('add');}
  function addTransitViaStop(lat,lon,name,address=''){if(!Number.isFinite(Number(lat))||!Number.isFinite(Number(lon)))return;transitViaStops.push({lat:Number(lat),lon:Number(lon),name:routePointName(name,address)||'Stop',address:address||'',source:'via'});finishRoutePointSearch();if(destination&&routeOrigin())calculateRoute();}
  function applyRoutePointSelection(lat,lon,label,address='',meta=null){
    lat=Number(lat);lon=Number(lon);if(!Number.isFinite(lat)||!Number.isFinite(lon))return;label=routePointName(label,address);
    if(pendingOriginSelection){originOverride={lat,lon,name:label||'Start location',address:address||'',meta:meta||null,source:'custom'};finishRoutePointSearch();if(destination)calculateRoute();return;}
    if(pendingDestinationSelection){finishRoutePointSearch();setDestination(lat,lon,label||'Destination',address,meta,{preserveStops:true,preserveOrigin:true,calculate:true});return;}
    if(pendingViaEditIndex>=0){const i=pendingViaEditIndex;if(i<transitViaStops.length)transitViaStops[i]={lat,lon,name:label||'Stop',address:address||'',meta:meta||null,source:'via'};finishRoutePointSearch();if(destination&&routeOrigin())calculateRoute();return;}
    if(pendingTransitStop){addTransitViaStop(lat,lon,label,address);return;}
    setDestination(lat,lon,label,address,meta);
  }
  function acceptSearchResult(r,label,address){applyRoutePointSelection(r.position.lat,r.position.lon,label,address,placeMetaFromResult(r));}

  function saveTransitPreferencesLocal(){try{localStorage.setItem('openroad.transitPrefs',JSON.stringify({preference:transitPreference,settings:transitPreferences}));}catch(_){}}
  function loadTransitPreferencesLocal(){try{const raw=JSON.parse(localStorage.getItem('openroad.transitPrefs')||'null');if(raw?.preference)transitPreference=raw.preference;if(raw?.settings){const legacy={...raw.settings};delete legacy.maxWalk;transitPreferences={...transitPreferences,...legacy,modes:{...transitPreferences.modes,...(legacy.modes||{})}};}}catch(_){}}

  function routePlannerIsOpen(){return !el('routePlannerDropdown')?.classList.contains('hidden');}
  function closeRoutePlanner(){show('routePlannerDropdown',false);el('topUi')?.classList.remove('route-planner-open');el('topUi')?.querySelector('.search-pill')?.classList.remove('route-planner-open');}
  function updateRoutePlannerSummary(){
    const box=el('routePlannerSelection'),out=el('routePlannerSelectionSummary');if(!box||!out)return;
    const route=routeResponse?.routes?.[selectedRoute];
    if(!route){show('routePlannerSelection',false);return;}
    let summary='';
    if(mode==='transit') summary=`${route.clearRouteDeparture||'—'} → ${route.clearRouteArrival||'—'} · ${formatTime(Number(route.summary?.travelTimeInSeconds)||0)}`;
    else summary=`${mode==='drive'?'Driving':mode==='cycle'?'Cycling':'Walking'} · ${routeSummary(route)}`;
    out.textContent=summary;show('routePlannerSelection',true);
  }
  function renderRoutePlanner(){
    renderTransitPlanner();updateRoutePlannerSummary();
  }
  function setRoutePlanningActive(active){
    routePlanningActive=!!active;
    const input=el('searchInput'),pill=el('topUi')?.querySelector('.search-pill');
    pill?.classList.toggle('route-active',routePlanningActive);
    const ptFlow = mode==='transit' && (routePlanningActive||!!transitNavigation);
    show('ptBackBtn',ptFlow);show('menuBtn',!ptFlow);
    show('routeSearchClearBtn',routePlanningActive||ptFlow);
    show('starBtn',!routePlanningActive&&!ptFlow);
    if(input){input.readOnly=routePlanningActive;if(routePlanningActive){input.value=destinationLabel||'Destination';input.placeholder='Destination';}else if(!destination){input.value='';input.placeholder='Where to?';}}
    if(!routePlanningActive)closeRoutePlanner();
  }
  function toggleRoutePlanner(){
    if(!routePlanningActive||!destination)return;
    const open=!routePlannerIsOpen();
    if(open){hideSearchDropdown();hideStarMenu();renderRoutePlanner();show('routePlannerDropdown');el('topUi')?.classList.add('route-planner-open');el('topUi')?.querySelector('.search-pill')?.classList.add('route-planner-open');}
    else closeRoutePlanner();
  }
  function haversineMeters(aLat,aLon,bLat,bLon){const R=6371000,toRad=v=>v*Math.PI/180,dLat=toRad(bLat-aLat),dLon=toRad(bLon-aLon),x=Math.sin(dLat/2)**2+Math.cos(toRad(aLat))*Math.cos(toRad(bLat))*Math.sin(dLon/2)**2;return 2*R*Math.atan2(Math.sqrt(x),Math.sqrt(1-x));}
  function minutesUntilClock(value){const m=parseClockMinutes(value);if(m==null)return null;const now=new Date(),cur=now.getHours()*60+now.getMinutes();let d=m-cur;if(d<-180)d+=1440;return d;}
  function transitNavigationInstruction(leg,dEnd){
    const m=normaliseTransitMode(leg?.mode),to=leg?.to||'the next stop',from=leg?.from||'this stop',line=leg?.line||'';
    if(m==='foot')return {icon:'🚶',text:`Walk to ${to}`,detail:formatDistance(dEnd)};
    const fromLat=Number(leg?.fromLat),fromLon=Number(leg?.fromLon),dStart=current&&Number.isFinite(fromLat)&&Number.isFinite(fromLon)?haversineMeters(current.lat,current.lon,fromLat,fromLon):9999;
    const dep=minutesUntilClock(leg?.liveDeparture||leg?.departure),nearStart=dStart<140&&(!Number.isFinite(dep)||dep>=-2);
    const vehicle=`${transitModeLabel(m)}${line?` ${line}`:''}`;
    if(nearStart)return {icon:transitModeIcon(m),text:`Board ${vehicle} at ${from}`,detail:(leg.liveDeparture||leg.departure)?`Departs ${leg.liveDeparture||leg.departure}`:'Board here'};
    if(dEnd<500)return {icon:transitModeIcon(m),text:`Get ready to leave at ${to}`,detail:leg.stopCount?`${leg.stopCount} stops on this leg`:formatDistance(dEnd)};
    return {icon:transitModeIcon(m),text:`Take ${vehicle} to ${to}`,detail:leg.stopCount?`${leg.stopCount} stops`:formatDistance(dEnd)};
  }
  function updateTransitNavigation(force=false){
    if(!transitNavigation||!navigating||mode!=='transit')return;
    const route=routeResponse?.routes?.[transitNavigation.routeIndex];const legs=route?.transitLegs||[];if(!route||!legs.length)return;
    let i=Math.min(transitNavigation.legIndex,legs.length-1),leg=legs[i];
    let toLat=Number(leg?.toLat),toLon=Number(leg?.toLon),dEnd=current&&Number.isFinite(toLat)&&Number.isFinite(toLon)?haversineMeters(current.lat,current.lon,toLat,toLon):Infinity;
    const threshold=normaliseTransitMode(leg?.mode)==='foot'?55:110;
    if(dEnd<=threshold&&i<legs.length-1){i++;transitNavigation.legIndex=i;leg=legs[i];toLat=Number(leg?.toLat);toLon=Number(leg?.toLon);dEnd=current&&Number.isFinite(toLat)&&Number.isFinite(toLon)?haversineMeters(current.lat,current.lon,toLat,toLon):Infinity;flashEdges('near');}
    if(i===legs.length-1&&dEnd<=35){el('navManeuverIcon').textContent='✓';el('instructionDistance').textContent='';el('instructionText').textContent='You have arrived';el('remainingTime').textContent='0 min';el('remainingDistance').textContent='Now';return;}
    const info=transitNavigationInstruction(leg,dEnd);el('navManeuverIcon').textContent=info.icon;el('instructionText').textContent=info.text;el('instructionDistance').textContent=info.detail;
    const arr=route.clearRouteArrival||'';el('arrivalTime').textContent=arr||formatArrivalTime(Number(route.summary?.travelTimeInSeconds)||0);
    const remaining=minutesUntilClock(arr);el('remainingTime').textContent=remaining==null?formatTime(Number(route.summary?.travelTimeInSeconds)||0):`${Math.max(0,remaining)} min`;
    el('remainingDistance').textContent=Number.isFinite(dEnd)?formatDistance(dEnd):'—';
    const navInstruction=el('navUi')?.querySelector('.nav-instruction');if(navInstruction)navInstruction.style.background=transitModeColour(leg?.mode,true);
    renderUserLocation(false);if(navigationFollow&&current)navigationCamera(current.lat,current.lon,current.hasBearing?current.bearing:map.getBearing(),force?300:600);
  }
  function startTransitNavigation(){
    const route=routeResponse?.routes?.[selectedRoute];if(!route?.transitLegs?.length)return toast('This journey does not contain navigable public-transport stages.');
    routeSelectionUserMade=true;transitNavigation={routeIndex:selectedRoute,legIndex:0};navigating=true;native()?.startTransitNavigation?.(selectedRoute);navigationFollow=true;angledView=false;updateViewButtons();closeRoutePlanner();show('routeCard',false);show('destinationCard',false);setNavigationChrome(true);el('navUi')?.classList.add('transit-navigation');show('navSpeedPanel',false);show('navAlongRouteBtn',false);show('navOptionsBtn',false);drawRoutes(true);updateTransitNavigation(true);
  }
  function stopTransitNavigation(){
    const was=!!transitNavigation;transitNavigation=null;navigating=false;native()?.stopTransitNavigation?.();navigationFollow=true;angledView=false;el('navUi')?.classList.remove('transit-navigation');const ni=el('navUi')?.querySelector('.nav-instruction');if(ni)ni.style.background='';setNavigationChrome(false);map?.easeTo({pitch:0,bearing:0,padding:{top:0,bottom:0,left:0,right:0},duration:350});if(was&&routeResponse){drawRoutes(false);show('routeCard');setRoutePlanningActive(true);}
  }

  function flashEdges(phase='early') {
    const node=el('edgeFlash');
    if(!node) return;
    node.classList.remove('active','near');
    void node.offsetWidth;
    if(phase==='near') node.classList.add('near');
    node.classList.add('active');
    setTimeout(()=>node.classList.remove('active','near'), 1550);
  }

  function routeVia(route) {
    if(route?.clearRouteVia) return route.clearRouteVia;
    const roads=[];
    (route?.sections||[]).forEach(section=>{
      if(section.sectionType!=='IMPORTANT_ROAD_STRETCH') return;
      (section.roadNumbers||[]).forEach(r=>{ if(r?.text && !roads.includes(r.text)) roads.push(r.text); });
    });
    return roads.slice(0,3).join(' · ');
  }

  function readFavourites() {
    try { return JSON.parse(native()?.getFavourites?.() || '[]') || []; } catch(_) { return []; }
  }

  function favouriteIndexFor(lat,lon) {
    const items=readFavourites();
    for(let i=0;i<items.length;i++) {
      if(Math.hypot(Number(items[i].lat)-lat,Number(items[i].lon)-lon)<0.00015) return i;
    }
    return -1;
  }

  function updateStarButton() {
    const btn=el('saveDestinationBtn'), rename=el('renameDestinationBtn'); if(!btn || !destination) return;
    const starred=favouriteIndexFor(destination.lat,destination.lon)>=0;
    btn.classList.toggle('starred',starred);
    const label=btn.querySelector('span'); if(label) label.textContent=starred?'Unstar':'Star';
    const svg=btn.querySelector('svg'); if(svg) svg.style.fill=starred?'currentColor':'none';
    show('renameDestinationBtn',starred);
  }

  function renameCurrentDestination(){
    if(!destination)return;
    const index=favouriteIndexFor(destination.lat,destination.lon);
    if(index<0)return toast('Star this place first, then you can rename it.');
    const item=readFavourites()[index]||{};
    openFavouriteNameEditor('Rename starred place',item.name||destinationLabel||'Starred place',name=>{
      native()?.renameFavourite?.(index,name);
      destinationLabel=name;
      if(el('selectedDestinationName'))el('selectedDestinationName').textContent=name;
      if(el('searchInput')&&routePlanningActive)el('searchInput').value=name;
      setTimeout(()=>{updateStarButton();if(poiVisible)renderStarredMarkers();renderRoutePlanner();},80);
    });
  }

  function renderDestinationMeta() {
    const box=el('selectedDestinationMeta'); if(!box) return;
    box.textContent='';
    const meta=destinationMeta||{};
    const parts=[];
    if(meta.category) parts.push(meta.category);
    if(meta.phone) parts.push(meta.phone);
    if(parts.length) box.append(document.createTextNode(parts.join(' · ')));
    if(meta.url){
      if(parts.length) box.append(document.createTextNode(' · '));
      const a=document.createElement('a'); a.textContent='Website'; a.href=meta.url.startsWith('http')?meta.url:`https://${meta.url}`; a.target='_blank'; a.rel='noopener'; box.append(a);
    }
    show('selectedDestinationMeta',!!box.textContent || !!meta.url);
  }

  function clearStarredMarkers() {
    starredMarkers.forEach(m=>{try{m.remove();}catch(_){}}); starredMarkers=[];
  }

  function updateStarredMarkerZoom() {
    if(!map) return;
    const zoom=Number(map.getZoom?.()||0);
    starredMarkers.forEach(marker=>{
      const node=marker?.getElement?.(); if(!node) return;
      const compact=zoom<10.5;
      node.classList.toggle('star-dot',compact);
      if(compact){
        const size=Math.max(5,Math.min(8,5+(zoom-5)*0.65));
        node.style.setProperty('--star-size',`${size}px`);
      } else {
        const size=Math.max(12,Math.min(23,12+(zoom-10.5)*2.2));
        node.style.setProperty('--star-size',`${size}px`);
      }
    });
  }

  function renderStarredMarkers() {
    clearStarredMarkers();
    if(!map || !mapLoaded || !poiVisible || placeCategories.starred===false) return;
    readFavourites().forEach(f=>{
      const lat=Number(f.lat), lon=Number(f.lon); if(!Number.isFinite(lat)||!Number.isFinite(lon)) return;
      const node=document.createElement('button'); node.type='button'; node.className='starred-map-marker';
      node.setAttribute('aria-label',f.name||'Starred place'); node.title=f.name||'Starred place';
      const glyph=document.createElement('span'); glyph.className='starred-map-glyph'; glyph.textContent='★';
      node.append(glyph); node.onclick=()=>setDestination(lat,lon,f.name||'Starred place','');
      try{ starredMarkers.push(new maplibregl.Marker({element:node,anchor:'center'}).setLngLat([lon,lat]).addTo(map)); }catch(_){}
    });
    updateStarredMarkerZoom();
  }

  function readPlaceCategories(){
    try{const raw=JSON.parse(localStorage.getItem('openroad.placeCategories')||'null');if(raw&&typeof raw==='object')placeCategories={...placeCategories,...raw};}catch(_){}
    try{const raw=JSON.parse(localStorage.getItem('openroad.contactPlaceCache')||'[]');if(Array.isArray(raw))contactPlaceCache=raw.filter(x=>Number.isFinite(Number(x.lat))&&Number.isFinite(Number(x.lon))).slice(0,100);}catch(_){}
  }
  function savePlaceCategories(){try{localStorage.setItem('openroad.placeCategories',JSON.stringify(placeCategories));}catch(_){} }
  function saveContactPlaceCache(){try{localStorage.setItem('openroad.contactPlaceCache',JSON.stringify(contactPlaceCache.slice(0,100)));}catch(_){} }
  function clearPlaceCategoryMarkers(category=null){
    const keys=category?[category]:[...placeCategoryMarkers.keys()];
    keys.forEach(key=>{(placeCategoryMarkers.get(key)||[]).forEach(m=>{try{m.remove();}catch(_){}});placeCategoryMarkers.delete(key);});
  }
  function renderContactPlaceMarkers(){
    clearPlaceCategoryMarkers('contacts');if(!mapLoaded||!poiVisible||!placeCategories.contacts)return;
    const markers=[];contactPlaceCache.forEach(c=>{const lat=Number(c.lat),lon=Number(c.lon);if(!Number.isFinite(lat)||!Number.isFinite(lon))return;const node=document.createElement('button');node.type='button';node.className='place-category-marker contacts';node.textContent='👤';node.title=c.name||'Contact';node.setAttribute('aria-label',c.name||'Contact');node.onclick=e=>{e.stopPropagation();setDestination(lat,lon,c.name||'Contact',c.address||'',{category:'Contact'});};try{markers.push(new maplibregl.Marker({element:node,anchor:'center'}).setLngLat([lon,lat]).addTo(map));}catch(_){}});placeCategoryMarkers.set('contacts',markers);
  }
  const contactGeocodeAttempted=new Set();
  function warmContactPlaceCache(){
    if(!placeCategories.contacts||!native()?.hasContactsPermission?.()||!native()?.getContactMapCandidates)return;
    if(localStorage.getItem('openroad.contactsMapGeocodingConsent')!=='yes')return;
    let all=[];try{all=JSON.parse(native().getContactMapCandidates()||'[]')||[];}catch(_){return;}
    const cached=new Set(contactPlaceCache.map(c=>`${c.name}|${c.address}`.toLowerCase()));
    let delay=0;
    all.slice(0,15).forEach(c=>{
      const key=`${c.name||'Contact'}|${c.address||''}`.toLowerCase();
      if(!c.address||cached.has(key)||contactBackgroundGeocodes.has(key)||contactGeocodeAttempted.has(key))return;
      contactGeocodeAttempted.add(key);
      contactBackgroundGeocodes.add(key);
      setTimeout(()=>{
        if(!placeCategories.contacts){contactBackgroundGeocodes.delete(key);return;}
        native()?.geocodeContactAddress?.(c.name||'Contact',c.address||'');
      },delay);
      delay+=600;
    });
  }
  function renderPlaceCategoryResults(category,data){
    clearPlaceCategoryMarkers(category);if(!mapLoaded||!poiVisible||!placeCategories[category])return;
    const meta=PLACE_CATEGORY_META[category];if(!meta)return;const markers=[];
    (data?.results||[]).filter(r=>r?.position&&Number.isFinite(Number(r.position.lat))&&Number.isFinite(Number(r.position.lon))).slice(0,30).forEach(r=>{const {label,address}=searchResultText(r),lat=Number(r.position.lat),lon=Number(r.position.lon);const node=document.createElement('button');node.type='button';node.className=`place-category-marker ${category}`;node.textContent=meta.symbol;node.title=label||meta.label;node.setAttribute('aria-label',label||meta.label);node.onclick=e=>{e.stopPropagation();setDestination(lat,lon,label||meta.label,address||'',placeMetaFromResult(r));};try{markers.push(new maplibregl.Marker({element:node,anchor:'center'}).setLngLat([lon,lat]).addTo(map));}catch(_){}});placeCategoryMarkers.set(category,markers);
  }
  function requestPlaceCategory(category){
    if(!mapLoaded||!map||!placeCategories[category]||!PLACE_CATEGORY_META[category]){clearPlaceCategoryMarkers(category);return;}
    let bounds;try{bounds=map.getBounds();}catch(_){return;}const ne=bounds.getNorthEast(),sw=bounds.getSouthWest(),id=-1000000-(++placeCategoryRequestSeq);placeCategoryRequests.set(id,category);native()?.searchMapArea?.(PLACE_CATEGORY_META[category].query,ne.lat,sw.lng,sw.lat,ne.lng,id);
  }
  function refreshPlaceCategories(){
    if(!mapLoaded)return;poiVisible=Object.values(placeCategories).some(Boolean);if(placeCategories.starred)renderStarredMarkers();else clearStarredMarkers();renderContactPlaceMarkers();if(placeCategories.contacts)warmContactPlaceCache();Object.keys(PLACE_CATEGORY_META).forEach(requestPlaceCategory);updateLayerButtons();
  }
  function schedulePlaceCategoryRefresh(){if(placeRefreshTimer)clearTimeout(placeRefreshTimer);placeRefreshTimer=setTimeout(()=>{placeRefreshTimer=0;refreshPlaceCategories();},650);}
  function openPlacesSheet(){document.querySelectorAll('[data-place-category]').forEach(cb=>{cb.checked=placeCategories[cb.dataset.placeCategory]!==false;});show('layersSheet',false);show('placesSheet');}
  function applyPlacesSheet(){const next={};document.querySelectorAll('[data-place-category]').forEach(cb=>next[cb.dataset.placeCategory]=!!cb.checked);
    if(next.contacts && localStorage.getItem('openroad.contactsMapGeocodingConsent')!=='yes'){
      if(!confirm('To put contacts on the map, OpenRoad must look up their postal addresses using the map provider. Only up to 15 addressed contacts are looked up on this phone. Continue?')){
        next.contacts=false;
      }else localStorage.setItem('openroad.contactsMapGeocodingConsent','yes');
    }
    placeCategories={...placeCategories,...next};savePlaceCategories();show('placesSheet',false);refreshPlaceCategories();
    if(placeCategories.contacts&&!native()?.hasContactsPermission?.())native()?.requestContactsPermission?.();
  }

  function contactMatches(query) {
    if(!contactsEnabled || !native()?.getContactMatches) return [];
    try { return JSON.parse(native().getContactMatches(query)||'[]')||[]; } catch(_) { return []; }
  }

  function makeContactPermissionRow() {
    const btn=document.createElement('button'); btn.className='result';
    const icon=document.createElement('span'); icon.className='search-contact-badge'; icon.textContent='☻';
    const name=document.createElement('div'); name.className='result-name'; name.textContent='Show contacts in search';
    const detail=document.createElement('div'); detail.className='result-address'; detail.textContent='Only contacts with postal addresses; stays on this phone';
    btn.append(icon,name,detail); btn.onclick=()=>native()?.requestContactsPermission?.(); return btn;
  }

  function appendContactRows(box, query) {
    if(!native()?.hasContactsPermission?.()) { box.appendChild(makeContactPermissionRow()); return; }
    const matches=contactMatches(query);
    matches.forEach(c=>{
      const btn=document.createElement('button'); btn.className='result contact-suggestion';
      const badge=document.createElement('span'); badge.className='search-contact-badge'; badge.textContent=(c.name||'?').trim().slice(0,1).toUpperCase();
      const name=document.createElement('div'); name.className='result-name'; name.textContent=c.name||'Contact';
      const detail=document.createElement('div'); detail.className='result-address'; detail.textContent=c.address||'';
      btn.append(badge,name,detail);
      btn.onclick=()=>{ btn.classList.add('loading');btn.disabled=true;el('searchInput').value=c.name||''; native()?.geocodeContactAddress?.(c.name||'Contact',c.address||''); };
      box.appendChild(btn);
    });
  }

  function clearAlongRouteMarkers(){
    if(alongRouteLayoutFrame){ cancelAnimationFrame(alongRouteLayoutFrame); alongRouteLayoutFrame=0; }
    alongRouteMarkers.forEach(m=>{try{m.remove();}catch(_){}}); alongRouteMarkers=[];
  }

  function rectOverlapArea(a,b,pad=7){
    const left=Math.max(a.left-pad,b.left-pad), right=Math.min(a.right+pad,b.right+pad);
    const top=Math.max(a.top-pad,b.top-pad), bottom=Math.min(a.bottom+pad,b.bottom+pad);
    return Math.max(0,right-left)*Math.max(0,bottom-top);
  }

  function markerCalloutCandidate(width,height,index,ring=0){
    const sideGap=18 + ring*20, verticalGap=18 + ring*16;
    const candidates=[
      {x:sideGap,y:-height-verticalGap},
      {x:-width-sideGap,y:-height-verticalGap},
      {x:sideGap,y:verticalGap},
      {x:-width-sideGap,y:verticalGap},
      {x:sideGap+10,y:-height/2},
      {x:-width-sideGap-10,y:-height/2},
      {x:-width/2,y:-height-verticalGap-12},
      {x:-width/2,y:verticalGap+12},
    ];
    return candidates[index % candidates.length];
  }

  function positionAlongRouteLeader(node,x,y,width,height){
    const line=node.querySelector('.along-route-leader'); if(!line) return;
    const nearestX=Math.max(x,Math.min(0,x+width));
    const nearestY=Math.max(y,Math.min(0,y+height));
    const length=Math.max(7,Math.hypot(nearestX,nearestY)-3);
    const angle=Math.atan2(nearestY,nearestX)*180/Math.PI;
    line.style.width=`${length}px`;
    line.style.transform=`rotate(${angle}deg)`;
  }

  function layoutAlongRouteMarkers(){
    alongRouteLayoutFrame=0;
    if(!map || !alongRouteMarkers.length) return;
    const container=map.getContainer?.(); if(!container) return;
    const viewport=container.getBoundingClientRect();
    const occupied=[];
    alongRouteMarkers.forEach((marker,markerIndex)=>{
      const node=marker.getElement?.(); const callout=node?.querySelector?.('.along-route-callout');
      if(!node || !callout) return;
      callout.style.transform='translate(18px,-44px)';
      const originRect=node.getBoundingClientRect();
      const measured=callout.getBoundingClientRect();
      const width=Math.max(54,measured.width), height=Math.max(28,measured.height);
      const originX=originRect.left+originRect.width/2, originY=originRect.top+originRect.height/2;
      let best=null;
      for(let ring=0;ring<4;ring++){
        for(let i=0;i<8;i++){
          const c=markerCalloutCandidate(width,height,(i+markerIndex)%8,ring);
          const rect={left:originX+c.x,top:originY+c.y,right:originX+c.x+width,bottom:originY+c.y+height};
          const overflow=Math.max(0,viewport.left+6-rect.left)+Math.max(0,rect.right-(viewport.right-6))+Math.max(0,viewport.top+6-rect.top)+Math.max(0,rect.bottom-(viewport.bottom-6));
          const overlap=occupied.reduce((sum,r)=>sum+rectOverlapArea(rect,r),0);
          const score=overlap+overflow*220+ring*5;
          if(!best || score<best.score) best={...c,rect,score};
          if(score===0) break;
        }
        if(best?.score===0) break;
      }
      if(!best) return;
      callout.style.transform=`translate(${Math.round(best.x)}px,${Math.round(best.y)}px)`;
      positionAlongRouteLeader(node,best.x,best.y,width,height);
      occupied.push(best.rect);
    });
  }

  function requestAlongRouteMarkerLayout(){
    if(alongRouteLayoutFrame || !alongRouteMarkers.length) return;
    alongRouteLayoutFrame=requestAnimationFrame(layoutAlongRouteMarkers);
  }
  function clearBusRouteMarkers(){
    busRouteMarkers.forEach(m=>{try{m.remove();}catch(_){}}); busRouteMarkers=[];busRouteStopData.clear();
    busLiveMarkers.forEach(m=>{try{m.remove();}catch(_){}}); busLiveMarkers=[];
    busRouteLayerIds.filter(id=>!id.endsWith('-src')).forEach(id=>{try{if(map?.getLayer(id))map.removeLayer(id);}catch(_){}});
    busRouteLayerIds.filter(id=>id.endsWith('-src')).forEach(id=>{try{if(map?.getSource(id))map.removeSource(id);}catch(_){}});
    busRouteLayerIds=[];
  }

  function geoDistanceSq(lat,lon,ref){if(!ref)return 0;const x=(lon-ref.lon)*Math.cos((lat+ref.lat)*Math.PI/360),y=lat-ref.lat;return x*x+y*y;}
  // Geographical tile for the selected service, never an unrelated previous route.
  // Prefer the section of the published route closest to the map viewport.
  function busLiveReference(data){
    const stops=Array.isArray(data?.stops)?data.stops:[];
    const points=stops.map(s=>({lat:Number(s.lat),lon:Number(s.lon)}))
      .filter(p=>Number.isFinite(p.lat)&&Number.isFinite(p.lon));
    if(!points.length){
      (Array.isArray(data?.geometries)?data.geometries:[]).forEach(g=>{
        (Array.isArray(g?.coordinates)?g.coordinates:[]).forEach(p=>{
          const lon=Number(p?.[0]),lat=Number(p?.[1]);
          if(Number.isFinite(lat)&&Number.isFinite(lon))points.push({lat,lon});
        });
      });
    }
    let focus=null;
    try{
      const c=map?.getCenter?.();
      if(c&&Number.isFinite(Number(c.lat))&&Number.isFinite(Number(c.lng)))
        focus={lat:Number(c.lat),lon:Number(c.lng)};
    }catch(_){}
    if(!focus&&current&&Number.isFinite(Number(current.lat))&&Number.isFinite(Number(current.lon)))
      focus={lat:Number(current.lat),lon:Number(current.lon)};
    if(!points.length)return focus;
    if(!focus)return points[0];
    return points.reduce((best,p)=>
      haversineMeters(p.lat,p.lon,focus.lat,focus.lon)<
      haversineMeters(best.lat,best.lon,focus.lat,focus.lon)?p:best,points[0]);
  }


  function renderBusServiceContent(){
    const data=busServiceData||{},box=el('busServiceContent');if(!box)return;box.textContent='';
    document.querySelectorAll('[data-bus-tab]').forEach(b=>b.classList.toggle('active',b.dataset.busTab===busServiceTab));
    if(busServiceTab==='about'){
      const about=document.createElement('div');about.className='bus-about';const vehicles=(data.vehicles||[]).length,stops=(data.stops||[]).length;
      about.textContent=`Route ${data.line||''} · ${data.source||'official public-transport data'}. ${stops?`${stops} published stops are available. `:''}${vehicles?`${vehicles} fresh live vehicle position${vehicles===1?' is':'s are'} currently known.`:'No fresh vehicle positions are currently available.'}`;box.appendChild(about);return;
    }
    if(busServiceTab==='timetable'){
      const timetable=data.timetable||{},deps=Array.isArray(timetable.departures)?timetable.departures:[];
      if(timetable.stopName){const intro=document.createElement('div');intro.className='bus-about';intro.textContent=`Upcoming scheduled departures from ${timetable.stopName}${timetable.direction?` · ${timetable.direction}`:''}`;box.appendChild(intro);}
      if(deps.length){deps.forEach(d=>{const row=document.createElement('div');row.className='bus-departure-row';const time=document.createElement('div');time.className='bus-departure-time';time.textContent=d.time||'—';const copy=document.createElement('div');copy.className='bus-departure-copy';const strong=document.createElement('strong');strong.textContent=d.destination||`Bus ${data.line||''}`;const small=document.createElement('small');small.textContent=d.direction||'Scheduled';copy.append(strong,small);row.append(time,copy);box.appendChild(row);});return;}
      const empty=document.createElement('div');empty.className='bus-about';empty.textContent='A stop-by-stop route is available below. A reliable timetable could not be extracted for this service at the moment.';box.appendChild(empty);
    }
    const stops=Array.isArray(data.stops)?data.stops:[];if(busServiceTab==='stops'||(busServiceTab==='timetable'&&!data.timetable?.departures?.length)){
      stops.slice(0,180).forEach((stop,i)=>{const row=document.createElement('button');row.type='button';row.className='bus-stop-row';const dot=document.createElement('span');dot.className='bus-stop-dot';const copy=document.createElement('span');const strong=document.createElement('strong');strong.textContent=stop.name||'Bus stop';const small=document.createElement('small');small.textContent=stop.direction?`${stop.direction} · stop ${i+1}`:`Stop ${i+1}`;copy.append(strong,small);const right=document.createElement('span');right.className='bus-stop-time';right.textContent=stop.time||'';row.append(dot,copy,right);row.onclick=()=>{const lat=Number(stop.lat),lon=Number(stop.lon);if(Number.isFinite(lat)&&Number.isFinite(lon)){map?.easeTo({center:[lon,lat],zoom:16,duration:450});openBusStop(stop);}};box.appendChild(row);});
    }
  }

  function renderBusLiveMarkers(){
    busLiveMarkers.forEach(m=>{try{m.remove();}catch(_){}});busLiveMarkers=[];
    const data=busServiceData||{},target=busServiceTargetStop;let vehicles=(Array.isArray(data.vehicles)?data.vehicles:[]).filter(v=>Number.isFinite(Number(v.lat))&&Number.isFinite(Number(v.lon)));if(target&&Number.isFinite(Number(target.lat))&&Number.isFinite(Number(target.lon))){vehicles=vehicles.filter(v=>{const d=haversineMeters(Number(v.lat),Number(v.lon),Number(target.lat),Number(target.lon));if(d<45)return true;const b=Number(v.bearing);if(!Number.isFinite(b))return false;return angleDifference(b,bearingTo(Number(v.lat),Number(v.lon),Number(target.lat),Number(target.lon)))<=95;}).sort((a,b)=>haversineMeters(Number(a.lat),Number(a.lon),Number(target.lat),Number(target.lon))-haversineMeters(Number(b.lat),Number(b.lon),Number(target.lat),Number(target.lon)));}else {const ref=busLiveReference(data);vehicles.sort((a,b)=>geoDistanceSq(Number(a.lat),Number(a.lon),ref)-geoDistanceSq(Number(b.lat),Number(b.lon),ref));}vehicles=vehicles.slice(0,3);
    vehicles.forEach(v=>{const lat=Number(v.lat),lon=Number(v.lon),node=document.createElement('div');node.className='bus-live-marker';if(v.lastKnown===true)node.style.opacity='.55';const bearing=Number(v.bearing),direction=document.createElement('span');direction.className='bus-live-direction';direction.textContent=Number.isFinite(bearing)?'➤':'🚌';if(Number.isFinite(bearing))direction.style.transform=`rotate(${bearing-90}deg)`;node.appendChild(direction);node.title=`${v.lastKnown===true?'Last known':'Live'} bus ${data.line||''}${v.destination?` to ${v.destination}`:''}${Number.isFinite(bearing)?' · direction of travel':''}`;try{busLiveMarkers.push(new maplibregl.Marker({element:node,anchor:'center'}).setLngLat([lon,lat]).addTo(map));}catch(_){}});
    const badge=el('busServiceLiveBadge');
    if(badge)badge.textContent=vehicles.length&&vehicles.every(v=>v.lastKnown===true)?'Last known':'Live';
    show('busServiceLiveBadge',vehicles.length>0);const btn=el('loadBusLiveBtn');if(btn){btn.classList.remove('loading');btn.disabled=false;btn.textContent=vehicles.length?(busServiceTargetStop?'Refresh next 3':'Refresh live buses'):(busServiceTargetStop?'Next 3 live buses':'Live buses');show('loadBusLiveBtn',data.liveAvailable!==false);}
  }

  // Stop repeated taps from exhausting the shared server's hourly BODS allowance.
  const busLiveAttemptTimes=new Map();
  let busLiveGlobalRetryUntil=0;
  function requestBusLive(){
    const data=busServiceData;if(!data?.line||!native()?.loadBusLiveVehicles)return;
    const ref=busServiceTargetStop||busLiveReference(data);if(!ref||!Number.isFinite(ref.lat)||!Number.isFinite(ref.lon))return toast('A location is needed to load nearby live buses.');
    const stamp=Date.now();
    if(stamp<busLiveGlobalRetryUntil){toast('The live-bus hourly allowance is exhausted. Please try later.');return;}
    const areaKey=`${String(data.line).toLowerCase()}|${Math.floor(ref.lat*20)}|${Math.floor(ref.lon*20)}`;
    if(stamp-(busLiveAttemptTimes.get(areaKey)||0)<120000){
      toast('Recently checked this service and area. Try again in about two minutes.');return;
    }
    busLiveAttemptTimes.set(areaKey,stamp);
    if(busLiveAttemptTimes.size>40)busLiveAttemptTimes.clear();
    const id=++busLiveRequestId,btn=el('loadBusLiveBtn');if(btn){btn.disabled=true;btn.classList.add('loading');btn.textContent='Loading live…';}
    native().loadBusLiveVehicles(String(data.line),ref.lat,ref.lon,id);
  }

  function drawBusRoute(data){
    ++busLiveRequestId;clearBusRouteMarkers();busServiceData=data||{};busServiceTab='timetable';
    if(!map || !mapLoaded || !data) return;
    const bounds=new maplibregl.LngLatBounds(); let hasBounds=false;
    const geometries=Array.isArray(data.geometries)?data.geometries:[];
    geometries.forEach((g,i)=>{
      const coords=(g?.coordinates||[]).filter(c=>Array.isArray(c)&&Number.isFinite(Number(c[0]))&&Number.isFinite(Number(c[1]))).map(c=>[Number(c[0]),Number(c[1])]);
      if(coords.length<2)return;const src=`bus-route-src-${i}`,line=`bus-route-line-${i}`;busRouteLayerIds.push(line,src);
      map.addSource(src,{type:'geojson',data:{type:'Feature',properties:{direction:g.direction||''},geometry:{type:'LineString',coordinates:coords}}});
      map.addLayer({id:line,type:'line',source:src,layout:{'line-join':'round','line-cap':'round'},paint:{'line-color':'#e53935','line-width':5,'line-opacity':.94}});coords.forEach(c=>{bounds.extend(c);hasBounds=true;});
    });
    const stops=Array.isArray(data.stops)?data.stops:[],stopFeatures=[];
    stops.slice(0,180).forEach((stop,i)=>{const lat=Number(stop.lat),lon=Number(stop.lon);if(!Number.isFinite(lat)||!Number.isFinite(lon))return;const key=`${String(stop.id||i)}|${lat.toFixed(6)}|${lon.toFixed(6)}`;busRouteStopData.set(key,stop);const bearing=stopTravelBearing(stops,i),properties={stopKey:key};if(bearing!==null)properties.bearing=bearing;stopFeatures.push({type:'Feature',properties,geometry:{type:'Point',coordinates:[lon,lat]}});bounds.extend([lon,lat]);hasBounds=true;});
    if(stopFeatures.length){const src='bus-route-stops-src',dots='bus-route-stop-dots',direction='bus-route-stop-direction',hit='bus-route-stop-hit';busRouteLayerIds.push(dots,direction,hit,src);map.addSource(src,{type:'geojson',data:{type:'FeatureCollection',features:stopFeatures}});map.addLayer({id:dots,type:'circle',source:src,paint:{'circle-radius':7,'circle-color':'#c62828','circle-stroke-color':'#ffffff','circle-stroke-width':2,'circle-opacity':1}});const icon=addStopDirectionIcon();if(icon)map.addLayer({id:direction,type:'symbol',source:src,filter:['has','bearing'],layout:{'icon-image':icon,'icon-size':.85,'icon-rotate':['get','bearing'],'icon-rotation-alignment':'map','icon-allow-overlap':true,'icon-ignore-placement':true}});map.addLayer({id:hit,type:'circle',source:src,paint:{'circle-radius':17,'circle-color':'#000000','circle-opacity':0}});}
    desaturateTransitJourney();
    if(hasBounds)map.fitBounds(bounds,{padding:{top:145,bottom:250,left:45,right:45},maxZoom:15.5,duration:650});
    el('busServiceNumber').textContent=data.line||'Bus';el('busServiceTitle').textContent=data.title||data.destination||`Bus ${data.line||''}`;el('busServiceSource').textContent=data.source||'Official route data';show('busServiceLiveBadge',false);const liveBtn=el('loadBusLiveBtn');if(liveBtn){liveBtn.disabled=false;liveBtn.classList.remove('loading');liveBtn.textContent=busServiceTargetStop?'Next 3 live buses':'Live buses';show('loadBusLiveBtn',data.liveAvailable!==false);}renderBusServiceContent();renderBusLiveMarkers();show('busServiceSheet');el('busServiceSheet').classList.remove('minimised');closeRoutePlanner();
  }

  function placeMetaFromResult(r){
    const poi=r?.poi||{}; const category=searchResultCategory(r)?.label||'';
    return {category,phone:poi.phone||'',url:poi.url||''};
  }


  function installLongPressDestination() {
    if (!map) return;
    const cancelLongPress = () => {
      if (longPressTimer) clearTimeout(longPressTimer);
      longPressTimer = null;
      longPressStartPoint = null;
      longPressStartLngLat = null;
    };

    map.on('touchstart', e => {
      if (navigating || !e.points || e.points.length !== 1) return cancelLongPress();
      cancelLongPress();
      longPressStartPoint = {x:e.point.x, y:e.point.y};
      longPressStartLngLat = {lat:e.lngLat.lat, lng:e.lngLat.lng};
      longPressTimer = setTimeout(() => {
        longPressTimer = null;
        if (!longPressStartLngLat || navigating) return;
        const point = longPressStartLngLat;
        if(routePointSelectionActive())applyRoutePointSelection(point.lat,point.lng,'Pin',`${point.lat.toFixed(5)}, ${point.lng.toFixed(5)}`);
        else setDestination(point.lat, point.lng, 'Pin', `${point.lat.toFixed(5)}, ${point.lng.toFixed(5)}`);
      }, 650);
    });
    map.on('touchmove', e => {
      if (!longPressTimer || !longPressStartPoint || !e.point) return;
      const dx=e.point.x-longPressStartPoint.x, dy=e.point.y-longPressStartPoint.y;
      if (Math.hypot(dx,dy) > 12 || (e.points && e.points.length !== 1)) cancelLongPress();
    });
    map.on('touchend', cancelLongPress);
    map.on('touchcancel', cancelLongPress);

    // Handy while testing in Android Studio with a mouse: right-click drops a pin too.
    map.on('contextmenu', e => {
      if (navigating) return toast('End navigation before choosing a new destination.');
      if(routePointSelectionActive())applyRoutePointSelection(e.lngLat.lat,e.lngLat.lng,'Pin',`${e.lngLat.lat.toFixed(5)}, ${e.lngLat.lng.toFixed(5)}`);
      else setDestination(e.lngLat.lat, e.lngLat.lng, 'Dropped pin', `${e.lngLat.lat.toFixed(5)}, ${e.lngLat.lng.toFixed(5)}`);
    });
  }

  function readTtsChoice() {
    try {
      const raw=native()?.getTtsChoice?.() || '';
      return raw ? JSON.parse(raw) : {engine:'',voice:''};
    } catch (_) { return {engine:'',voice:''}; }
  }

  function readTtsEngines() {
    try {
      const raw=native()?.getTtsEngines?.() || '[]';
      const list=JSON.parse(raw);
      return Array.isArray(list) ? list : [];
    } catch (_) { return []; }
  }

  function ttsEngineLabel(pkg) {
    if(!pkg) return 'System default';
    return ttsEngines.find(x=>x.package===pkg)?.label || pkg;
  }

  function refreshVoiceSummary() {
    ttsChoice=readTtsChoice();
    const engine=ttsEngineLabel(ttsChoice.engine);
    const voice=ttsChoice.voice ? ttsChoice.voice : 'engine default UK voice';
    el('voiceSummary').textContent=`${engine} • ${voice}`;
  }

  function voiceLabel(v) {
    const locale=(v.locale||'English').replace('-', '‑');
    const network=v.network ? 'network' : 'offline';
    return `${locale} — ${v.name} (${network})`;
  }

  function requestVoicesForSelectedEngine() {
    const engine=el('ttsEngineSelect').value || '';
    el('ttsVoiceSelect').disabled=true;
    el('ttsVoiceSelect').innerHTML='<option value="">Loading voices…</option>';
    el('voiceLoadStatus').textContent='Reading voices from the selected engine…';
    native()?.requestTtsVoices?.(engine);
  }

  function openVoiceSetup() {
    ttsChoice=readTtsChoice();
    ttsEngines=readTtsEngines();
    const engineSelect=el('ttsEngineSelect');
    engineSelect.textContent='';
    const system=document.createElement('option'); system.value=''; system.textContent='System default'; engineSelect.appendChild(system);
    ttsEngines.forEach(engine=>{
      const opt=document.createElement('option'); opt.value=engine.package; opt.textContent=engine.label || engine.package; engineSelect.appendChild(opt);
    });
    const hasSavedEngine=!ttsChoice.engine || [...engineSelect.options].some(o=>o.value===ttsChoice.engine);
    engineSelect.value=hasSavedEngine ? (ttsChoice.engine||'') : '';
    show('settings',false); show('voiceSetup');
    requestVoicesForSelectedEngine();
  }

  function signalNativeReady() {
    if (nativeReadySignalled) return;
    nativeReadySignalled = true;
    native()?.appReady?.();
  }

  function finishMapSetup() {
    if (mapLoaded || !map) return;
    mapLoaded = true;
    capturePoiVisibility();
    ensureCyclewayLayer();
    updateLayerButtons();
    if (current) { renderUserLocation(!initialLocationCentred); initialLocationCentred=true; }
    if (destination) renderDestinationMarker();
    if (routeResponse) drawRoutes(navigating);
    if (trafficVisible) addTrafficLayers();
    // Keep generic POIs hidden; selected Places categories are rendered explicitly.
    poiLayers().forEach(id=>{try{map.setLayoutProperty(id,'visibility','none');}catch(_){}});
    if (poiVisible) refreshPlaceCategories();
    signalNativeReady();
  }

  function initMap() {
    if (typeof maplibregl === 'undefined') {
      toast('Map engine did not load. Rebuild OpenRoad and reinstall it.');
      signalNativeReady();
      return;
    }
    try {
      map = new maplibregl.Map({
        container:'map',
        // The OpenFreeMap Bright style proved clearer in real-world testing than the
        // custom OpenRoad palette, so it is now the normal map rather than a fallback.
        style:'https://tiles.openfreemap.org/styles/bright',
        center:[-2.58,54.3], zoom:5.4,
        attributionControl:true,
        maxPitch:65
      });
      map.dragRotate.disable();
      map.touchZoomRotate.disableRotation();
      installLongPressDestination();
      map.on('click', e => {
        hideSearchDropdown(); hideStarMenu(); closeRoutePlanner();
        if(!navigating && map.getLayer('bus-route-stop-hit')){
          const stops=map.queryRenderedFeatures(e.point,{layers:['bus-route-stop-hit']});
          const key=stops?.[0]?.properties?.stopKey;
          if(key && busRouteStopData.has(key)){openBusStop(busRouteStopData.get(key));return;}
        }
        if(!navigating && map.getLayer('route-transit-stop-hit')){
          const stops=map.queryRenderedFeatures(e.point,{layers:['route-transit-stop-hit']});
          const key=stops?.[0]?.properties?.stopKey;
          if(key && transitStopData.has(key)){openBusStop(transitStopData.get(key));return;}
        }
        if(navigating) return;
        if(routeResponse?.routes?.length) {
          const layers=routeResponse.routes.map((_,i)=>`route-hit-${i}`).filter(id=>map.getLayer(id));
          if(layers.length){
            const features=map.queryRenderedFeatures(e.point,{layers});
            if(features.length){ const idx=Number(features[0].properties?.routeIndex); if(Number.isInteger(idx)){selectRoute(idx,true);return;} }
          }
        }
        // Bright's useful non-sponsored place labels can be tapped like a normal map.
        const placeLayers=poiLayers().filter(id=>map.getLayer(id));
        if(placeLayers.length){
          const features=map.queryRenderedFeatures(e.point,{layers:placeLayers});
          const feature=features.find(f=>f?.properties?.name || f?.properties?.['name:latin']);
          if(feature){
            const name=feature.properties.name || feature.properties['name:latin'];
            const kind=feature.properties.class || feature.properties.subclass || '';
            setDestination(e.lngLat.lat,e.lngLat.lng,name,kind ? String(kind).replace(/_/g,' ') : '',{category:kind ? String(kind).replace(/_/g,' ') : ''});
            native()?.requestPlaceDetails?.(name,e.lngLat.lat,e.lngLat.lng);
          }
        }
      });

      // During navigation, a deliberate pan/zoom means "let me inspect the map".
      // Stop camera-follow until the user taps Recentre instead of fighting their gesture.
      const suspendFollow = event => {
        if (!navigating || !event?.originalEvent) return;
        navigationFollow = false;
        updateMapActionVisibility();
      };
      map.on('dragstart', suspendFollow);
      map.on('zoomstart', suspendFollow);
      map.on('move', requestAlongRouteMarkerLayout);
      map.on('zoom', updateStarredMarkerZoom);
      map.on('rotate', requestAlongRouteMarkerLayout);
      map.on('resize', requestAlongRouteMarkerLayout);
      map.on('moveend', ()=>{schedulePlaceCategoryRefresh();if(pendingTransitOverlayRefresh&&routeResponse){pendingTransitOverlayRefresh=false;drawRoutes(navigating,false);}});

      map.on('load', finishMapSetup);
      map.on('error', event => console.error('MapLibre error', event?.error || event));

      // Native location/navigation state must not depend on remote map resources finishing.
      signalNativeReady();
      setTimeout(() => {
        if (!mapLoaded) toast("The map is taking a while to load. Check the phone's internet connection.");
      }, 10000);
    } catch (e) {
      console.error(e);
      toast('Could not start the map on this phone.');
      signalNativeReady();
    }
  }

  function poiLayers() {
    if (!map?.isStyleLoaded()) return [];
    const pattern=/(poi|amenity|shop|restaurant|cafe|bar|pub|hotel|hostel|tourism|attraction|museum|cinema|theatre|hospital|pharmacy|parking|fuel|bank|atm|school|college|university|station|transit)/i;
    return (map.getStyle().layers||[]).filter(layer=>pattern.test(layer.id)||pattern.test(layer['source-layer']||'')).map(layer=>layer.id);
  }

  function capturePoiVisibility() {
    poiLayerDefaults.clear();
    poiLayers().forEach(id=>{
      try { poiLayerDefaults.set(id,map.getLayoutProperty(id,'visibility') || 'visible'); } catch(_) { poiLayerDefaults.set(id,'visible'); }
    });
  }

  function setPoiVisibility(visible) {
    poiVisible=!!visible;
    // OpenRoad uses explicit category pins rather than the base map's generic POI clutter.
    poiLayers().forEach(id=>{try{map.setLayoutProperty(id,'visibility','none');}catch(_){}});
    if(poiVisible)refreshPlaceCategories();else{clearStarredMarkers();clearPlaceCategoryMarkers();}
    updateLayerButtons();
  }

  function updateLayerButtons() {
    el('trafficLayerBtn')?.classList.toggle('active',trafficVisible);
    el('cycleLayerBtn')?.classList.toggle('active',cycleLayerVisible);
    el('placesLayerBtn')?.classList.toggle('active',poiVisible && Object.values(placeCategories).some(Boolean));
  }

  function ensureCyclewayLayer() {
    if (!map?.isStyleLoaded() || map.getLayer('clearroute-cycleways')) return;
    try {
      const transportLayer=(map.getStyle().layers||[]).find(layer => layer['source-layer']==='transportation' && layer.source);
      if(!transportLayer) return;
      map.addLayer({
        id:'clearroute-cycleways', type:'line', source:transportLayer.source, 'source-layer':'transportation', minzoom:11,
        filter:['any',['==',['get','subclass'],'cycleway'],['==',['get','class'],'cycleway']],
        layout:{'line-cap':'round','line-join':'round',visibility:cycleLayerVisible?'visible':'none'},
        paint:{'line-color':'#4f9678','line-opacity':0.9,'line-width':['interpolate',['linear'],['zoom'],11,1.2,15,2.4,19,4],'line-dasharray':[2,1.5]}
      });
    } catch(e) { console.log('Could not add cycleway overlay',e); }
  }

  function addTrafficLayers() {
    if (!map?.isStyleLoaded() || !trafficVisible || !native()?.hasApiKey()) return;
    const key = encodeURIComponent(native().getTrafficApiKey());
    try {
      if (!map.getSource('tomtom-flow')) {
        map.addSource('tomtom-flow', {type:'raster', tileSize:256, tiles:[`https://api.tomtom.com/maps/orbis/traffic/flow/raster/tile/{z}/{x}/{y}?apiVersion=2&style=light&tileSize=256&key=${key}`]});
        map.addLayer({id:'tomtom-flow-layer', type:'raster', source:'tomtom-flow', paint:{'raster-opacity':0.67}});
      }
      if (!map.getSource('tomtom-incidents')) {
        map.addSource('tomtom-incidents', {type:'raster', tileSize:256, tiles:[`https://api.tomtom.com/maps/orbis/traffic/incidents/raster/tile/{z}/{x}/{y}?apiVersion=2&style=light&tileSize=256&key=${key}`]});
        map.addLayer({id:'tomtom-incidents-layer', type:'raster', source:'tomtom-incidents', paint:{'raster-opacity':0.9}});
      }
    } catch (e) { console.log(e); }
  }

  function removeTrafficLayers() {
    ['tomtom-incidents-layer','tomtom-flow-layer'].forEach(id => { if(map?.getLayer(id)) map.removeLayer(id); });
    ['tomtom-incidents','tomtom-flow'].forEach(id => { if(map?.getSource(id)) map.removeSource(id); });
  }

  function setMode(next, recalculate=true) {
    const previousMode=mode;
    mode = ['drive','cycle','walk','transit'].includes(next) ? next : 'drive';
    native()?.setTravelMode?.(mode);
    if(mode==='transit'){const origin=routeOrigin();if(origin)native()?.prepareTransitData?.(origin.lat,origin.lon);}
    ['drive','cycle','walk','transit'].forEach(m=>el(`${m}Btn`)?.classList.toggle('active',mode===m));
    show('routePreferencesBtn', mode==='drive');
    closeRoutePlanner();
    show('transitResultsToolbar',mode==='transit' && !!routeResponse && !navigating);
    el('routeCard')?.classList.toggle('transit-active',mode==='transit');
    el('routeOptions')?.classList.toggle('transit-results',mode==='transit');
    renderRoutePlanner();
    if (mode==='cycle') cycleLayerVisible=true;
    if(map?.getLayer('clearroute-cycleways')) {
      try { map.setLayoutProperty('clearroute-cycleways','visibility',cycleLayerVisible?'visible':'none'); } catch(_) {}
    }
    if (trafficVisible) addTrafficLayers(); else removeTrafficLayers();
    updateLayerButtons();
    updateMapActionVisibility();
    if (recalculate && destination && routeOrigin() && !navigating) calculateRoute();
  }

  function updateUserHeading() {
    if(!userMarker || !current) return;
    const marker=userMarker.getElement();
    const heading=marker.querySelector('.user-heading');
    if(!heading) return;
    const usable=!!current.hasBearing;
    heading.classList.toggle('hidden-heading',!usable);
    if(usable) heading.style.transform=`rotate(${(current.bearing||0)-(map?.getBearing?.()||0)}deg)`;
  }

  function renderUserLocation(centre=false) {
    if (!map || !current) return;
    try {
      if (!userMarker) {
        const marker=document.createElement('div'); marker.className='user-position';
        const heading=document.createElement('div'); heading.className='user-heading';
        const dot=document.createElement('div'); dot.className='user-dot';
        marker.append(heading,dot);
        userMarker=new maplibregl.Marker({element:marker,anchor:'center'}).setLngLat([current.lon,current.lat]).addTo(map);
        map.on('rotate',updateUserHeading);
      } else userMarker.setLngLat([current.lon,current.lat]);
      updateUserHeading();
      if (centre) map.easeTo({center:[current.lon,current.lat],zoom:15.5,duration:600});
    } catch (e) { console.error('Could not render current location', e); }
  }

  function navigationCamera(lat,lon,bearing,duration=650) {
    if(!map) return;
    const h=Math.max(480,window.innerHeight||720);
    const heading=Number.isFinite(Number(bearing)) ? Number(bearing) : map.getBearing();
    const zoom=mode==='walk'?18.0:(mode==='cycle'?17.4:17.0);
    const pitch=angledView ? (mode==='walk'?32:(mode==='cycle'?42:50)) : 0;
    map.easeTo({
      center:[lon,lat], bearing:heading, pitch, zoom, duration,
      padding:{top:Math.round(h*.28),bottom:Math.round(h*.08),left:34,right:34}
    });
  }

  function updateViewButtons() {
    const targetLabel = angledView ? '2D' : '3D';
    ['viewToggleBtn','navViewToggleBtn'].forEach(id => {
      const button=el(id); if(!button) return;
      button.textContent=targetLabel;
      button.title=angledView ? 'Switch to straight-down view' : 'Switch to angled view';
      button.setAttribute('aria-label', button.title);
    });
  }

  function toggleMapView() {
    angledView = !angledView;
    updateViewButtons();
    if (!map) return;
    if (navigating && navigationFollow && current) {
      navigationCamera(current.lat,current.lon,current.hasBearing?current.bearing:map.getBearing(),450);
    } else {
      map.easeTo({pitch:angledView?45:0,duration:400});
    }
  }

  function syncLocateButtonHost() {
    const locate=el('locateBtn'), normalHost=el('mapActions'), navigationHost=el('navMapActions');
    if(!locate || !normalHost || !navigationHost) return;
    const target=navigating ? navigationHost : normalHost;
    if(locate.parentElement!==target) target.appendChild(locate);
    locate.classList.toggle('nav-control', navigating);
  }

  function updateMapActionVisibility() {
    syncLocateButtonHost();
    show('mapActions', !navigating);
    show('layersBtn', !navigating);
    show('viewToggleBtn', !navigating);
    const locate = el('locateBtn');
    const showLocate = !navigating || !navigationFollow;
    show('locateBtn', showLocate);
    if (locate) {
      locate.classList.toggle('recenter-mode', navigating && !navigationFollow);
      const label = navigating && !navigationFollow ? 'Recentre on my location' : 'Centre on my location';
      locate.title = label;
      locate.setAttribute('aria-label', label);
    }
  }

  function recentreNavigation() {
    if (!navigating || !current) return;
    navigationFollow = true;
    updateMapActionVisibility();
    navigationCamera(current.lat,current.lon,current.hasBearing?current.bearing:map.getBearing(),450);
  }

  function setNavigationChrome(active) {
    show('topUi', !active);
    show('modeSwitch', !active);
    show('navUi', active);
    show('navMapActions', active);
    show('navSpeedPanel', active && mode==='drive');
    show('navAlongRouteBtn', active && mode!=='transit');
    show('navOptionsBtn', active && mode!=='transit');
    show('navSoundBtn', active && mode!=='transit');
    if(!active) { show('navOptions', false); show('alongRouteSheet', false); }
    updateMapActionVisibility();
  }

  function navigationSymbol(maneuver='', message='') {
    const m=(maneuver||'').toUpperCase();
    const text=(message||'').toLowerCase();
    if(m.includes('ROUNDABOUT') || text.includes('roundabout')) return '⟳';
    if(m.includes('UTURN') || m.includes('U_TURN') || text.includes('u-turn')) return '↶';
    if(m.includes('KEEP_LEFT') || text.includes('keep left')) return '↖';
    if(m.includes('KEEP_RIGHT') || text.includes('keep right')) return '↗';
    if(m.includes('LEFT') || text.includes('turn left')) return '←';
    if(m.includes('RIGHT') || text.includes('turn right')) return '→';
    if(m.includes('RAMP') && text.includes('left')) return '↖';
    if(m.includes('RAMP')) return '↗';
    return '↑';
  }

  function renderDestinationMarker() {
    if (!map || !destination) return;
    try {
      if (destMarker) destMarker.remove();
      const pin=document.createElement('div'); pin.className='dest-pin';
      pin.innerHTML='<svg viewBox="0 0 28 38" aria-hidden="true"><path d="M14 1C6.8 1 1 6.8 1 14c0 10 13 23 13 23s13-13 13-23C27 6.8 21.2 1 14 1Z"/><circle cx="14" cy="14" r="5"/></svg>';
      // The SVG tip is exactly at the element bottom. Keeping the geographic anchor on that
      // tip prevents the apparent pin drift that a rotated CSS shape caused while zooming.
      destMarker = new maplibregl.Marker({element:pin,anchor:'bottom'}).setLngLat([destination.lon,destination.lat]).addTo(map);
    } catch (e) { console.error('Could not render destination marker', e); }
  }

  function searchResultCategory(r) {
    const poi=r?.poi||{};
    const categories=[];
    if(Array.isArray(poi.categories)) categories.push(...poi.categories.map(String));
    if(Array.isArray(poi.classifications)) poi.classifications.forEach(c=>{
      if(c?.code) categories.push(String(c.code));
      if(Array.isArray(c?.names)) c.names.forEach(n=>categories.push(String(n?.name||n||'')));
    });
    const haystack=[poi.name||'',...categories,r?.type||'',r?.address?.streetName||''].join(' ').toLowerCase();
    const match=(rx,symbol,label)=>rx.test(haystack)?{symbol,label}:null;
    return match(/petrol|gas station|fuel|service station|charging station|ev charging/, '⛽', 'Fuel') ||
      match(/\bpub\b|bar|nightlife|beer|brewery/, '🍺', 'Pub or bar') ||
      match(/cafe|coffee|tea room/, '☕', 'Cafe') ||
      match(/restaurant|food|fast food|takeaway/, '🍴', 'Food') ||
      match(/supermarket|grocery|convenience|shopping|shop|store|market/, '🛒', 'Shop') ||
      match(/rest area|rest stop|services/, '🛣', 'Rest stop') ||
      match(/toilet|restroom|public convenience/, '🚻', 'Toilets') ||
      match(/parking|car park/, 'P', 'Parking') ||
      match(/pharmacy|chemist/, '✚', 'Pharmacy') ||
      match(/hospital|clinic|medical|doctor/, '✚', 'Healthcare') ||
      match(/train|railway|station/, '🚉', 'Rail station') ||
      match(/bus station|bus stop|coach/, '🚌', 'Bus') ||
      match(/airport|aerodrome/, '✈', 'Airport') ||
      match(/hotel|motel|lodging|accommodation/, '▦', 'Hotel') ||
      match(/atm|cash machine/, '£', 'Cash machine') ||
      match(/bank|financial/, '£', 'Bank') ||
      match(/school|college|university/, '◆', 'Education') ||
      match(/park|garden|recreation|playground/, '♣', 'Park') ||
      match(/cinema|theatre|museum|arts|entertainment/, '★', 'Attraction') ||
      {symbol:'⌖',label:'Place'};
  }

  function makeResultIcon(r, className='result-symbol') {
    const category=searchResultCategory(r);
    const icon=document.createElement('span');
    icon.className=className;
    icon.textContent=category.symbol;
    icon.setAttribute('aria-label',category.label);
    icon.title=category.label;
    return icon;
  }

  function searchResultText(r) {
    const label=r?.poi?.name || r?.address?.freeformAddress || r?.address?.streetName || 'Destination';
    const address=r?.address?.freeformAddress || '';
    return {label,address};
  }

  function hideSearchDropdown() { show('searchSuggestionsDropdown', false); }
  function hideStarMenu() { show('starMenuDropdown', false); }

  function renderStarMenu() {
    const box=el('starMenuItems');
    if(!box) return;
    box.textContent='';
    home=readHome();
    const homeRow=document.createElement('button');
    homeRow.className='star-menu-row';
    homeRow.innerHTML='<span class="star-menu-icon">⌂</span><span class="star-menu-copy"><strong>Home</strong><small></small></span><span class="settings-chevron">›</span>';
    homeRow.querySelector('small').textContent=home ? (home.address||home.name||'Home') : 'Set your Home address';
    homeRow.onclick=()=>{
      hideStarMenu();
      if(home) goHome();
      else { show('settings'); setTimeout(()=>el('setHomeBtn')?.focus(),80); }
    };
    box.appendChild(homeRow);

    const saved=readFavourites();
    saved.forEach(f=>{
      const row=document.createElement('button'); row.className='star-menu-row';
      row.innerHTML='<span class="star-menu-icon">★</span><span class="star-menu-copy"><strong></strong><small>Starred place</small></span><span class="settings-chevron">›</span>';
      row.querySelector('strong').textContent=f.name||'Starred place';
      row.onclick=()=>{ hideStarMenu(); setDestination(Number(f.lat),Number(f.lon),f.name||'Starred place',''); requestDirections(); };
      box.appendChild(row);
    });
    if(!saved.length){
      const empty=document.createElement('div'); empty.className='search-dropdown-status'; empty.textContent='No starred places yet'; box.appendChild(empty);
    }
  }

  function toggleStarMenu() {
    const menu=el('starMenuDropdown');
    const opening=menu?.classList.contains('hidden');
    hideSearchDropdown();
    if(opening){ renderStarMenu(); show('starMenuDropdown'); }
    else hideStarMenu();
  }

  function clearAreaSearchMarkers() {
    areaSearchMarkers.forEach(marker=>{ try{marker.remove();}catch(_){} });
    areaSearchMarkers=[];
  }

  function makeSearchAreaAction(query) {
    const btn=document.createElement('button');
    btn.className='search-area-action';
    const name=document.createElement('div'); name.className='result-name'; name.textContent='Search current map area';
    const detail=document.createElement('div'); detail.className='result-address'; detail.textContent=`Find “${query}” in the map you can see`;
    btn.append(name,detail);
    btn.onclick=()=>searchCurrentMapArea(query);
    return btn;
  }

  function makeBusRouteInfoAction(query) {
    const btn=document.createElement('button'); btn.className='result';
    const icon=document.createElement('span'); icon.className='search-contact-badge'; icon.textContent='🚌';
    const clean=query.replace(/^\s*bus\s+/i,'').trim();
    const name=document.createElement('div'); name.className='result-name'; name.textContent=`Show bus ${clean} on map`;
    const detail=document.createElement('div'); detail.className='result-address';
    detail.textContent='Official TfL route geometry in London; fresh BODS vehicle positions elsewhere in England';
    btn.append(icon,name,detail);
    btn.onclick=()=>{hideSearchDropdown();busServiceTargetStop=null;++busLiveRequestId;busServiceReturnSheet=el('routeCard')&&!el('routeCard').classList.contains('hidden')?'routeCard':'none';const id=++busRouteRequestId;toast(`Finding bus ${clean}…`);const focus=map?.getCenter?.();if(focus&&Number.isFinite(Number(focus.lat))&&Number.isFinite(Number(focus.lng))&&native()?.lookupBusRouteNear)native().lookupBusRouteNear(clean,Number(focus.lat),Number(focus.lng),id);else native()?.lookupBusRoute?.(clean,id);};
    return btn;
  }

  function makeUseMyLocationAction(){
    const btn=document.createElement('button');btn.type='button';btn.className='result';
    const icon=document.createElement('span');icon.className='search-contact-badge';icon.textContent='●';
    const name=document.createElement('div');name.className='result-name';name.textContent='My location';
    const detail=document.createElement('div');detail.className='result-address';detail.textContent=current?'Use your current position as the start':'Use your current position when it becomes available';
    btn.append(icon,name,detail);btn.onclick=()=>{originOverride=null;finishRoutePointSearch();if(destination)requestDirections();};return btn;
  }

  function renderSearchDropdown(data, status='') {
    const query=el('searchInput').value.trim();
    const box=el('searchSuggestions'); box.textContent='';
    if(pendingOriginSelection)box.appendChild(makeUseMyLocationAction());
    if(query.length<2){if(pendingOriginSelection)show('searchSuggestionsDropdown',true);else hideSearchDropdown();return;}
    appendContactRows(box,query);
    box.appendChild(makeSearchAreaAction(query));
    if(/^\s*(?:bus\s+)?[a-z]?\d+[a-z]?\s*$/i.test(query)) box.appendChild(makeBusRouteInfoAction(query));
    if(status){
      const info=document.createElement('div'); info.className='search-dropdown-status'; info.textContent=status; box.appendChild(info);
    }
    const results=data?.results||[];
    results.forEach(r=>{
      if(!r?.position) return;
      const {label,address}=searchResultText(r);
      const btn=document.createElement('button'); btn.className='result';
      const icon=makeResultIcon(r);
      const name=document.createElement('div'); name.className='result-name'; name.textContent=label;
      const addressNode=document.createElement('div'); addressNode.className='result-address'; addressNode.textContent=address;
      btn.append(icon,name,addressNode);
      btn.onclick=()=>acceptSearchResult(r,label,address);
      box.appendChild(btn);
    });
    show('searchSuggestionsDropdown',true);
  }

  function requestSearchSuggestions(requestId=null) {
    const q=el('searchInput').value.trim();
    if(q.length<2){hideSearchDropdown();return;}
    const id=requestId ?? ++suggestionRequestId;
    renderSearchDropdown(null,'Searching…');
    native()?.searchSuggestions?.(q,el('searchBias').checked,id);
  }

  function searchCurrentMapArea(query) {
    if(!map || !query || query.trim().length<2) return;
    ++suggestionRequestId; ++searchRequestId;
    let bounds;
    try { bounds=map.getBounds(); } catch(_) { return toast('The map area is not ready yet.'); }
    const ne=bounds.getNorthEast(), sw=bounds.getSouthWest();
    const id=++mapAreaSearchRequestId;
    hideSearchDropdown(); clearAreaSearchMarkers();
    toast('Searching this map area…');
    native()?.searchMapArea?.(query.trim(),ne.lat,sw.lng,sw.lat,ne.lng,id);
  }

  function showAreaSearchResults(data) {
    clearAreaSearchMarkers();
    const results=(data?.results||[]).filter(r=>r?.position && Number.isFinite(Number(r.position.lat)) && Number.isFinite(Number(r.position.lon)));
    if(!results.length){toast('No matching places in the current map area.');return;}
    results.forEach(r=>{
      const {label,address}=searchResultText(r);
      const node=document.createElement('button'); node.type='button'; node.className='area-search-marker'; node.setAttribute('aria-label',label);
      const pin=document.createElement('span'); pin.className='area-search-pin';
      const category=searchResultCategory(r); pin.textContent=category.symbol; pin.title=category.label;
      const text=document.createElement('span'); text.className='area-search-label'; text.textContent=label;
      node.append(pin,text);
      node.onclick=event=>{
        event.stopPropagation();
        if(routePointSelectionActive())applyRoutePointSelection(Number(r.position.lat),Number(r.position.lon),label,address,placeMetaFromResult(r));
        else{el('searchInput').value=label;setDestination(Number(r.position.lat),Number(r.position.lon),label,address);}
        clearAreaSearchMarkers();
      };
      try {
        const marker=new maplibregl.Marker({element:node,anchor:'bottom'}).setLngLat([Number(r.position.lon),Number(r.position.lat)]).addTo(map);
        areaSearchMarkers.push(marker);
      } catch(_) {}
    });
    toast(`${areaSearchMarkers.length} ${areaSearchMarkers.length===1?'place':'places'} found in this map area.`);
  }

  function stopTransitSearchWatchdog(){
    if(transitSearchTimer){clearTimeout(transitSearchTimer);transitSearchTimer=0;}
    transitSearchRequest=0;
  }
  function showTransitSearchFailure(message){
    const container=el('routeOptions');
    if(!container)return;
    // Preserve an already visible, usable route if a refresh fails.
    if(routeResponse?.routes?.length){toast(message);return;}
    container.classList.add('transit-results');
    container.textContent='';
    const panel=document.createElement('div');panel.className='transit-search-failed';
    const heading=document.createElement('strong');heading.textContent='Public transport search stopped';
    const detail=document.createElement('span');detail.textContent=String(message||'No route was found.');
    const retry=document.createElement('button');retry.type='button';retry.className='transit-search-retry';retry.textContent='Try again';
    retry.onclick=()=>calculateRoute();panel.append(heading,detail,retry);container.appendChild(panel);
    show('routeCard',true);show('destinationCard',false);show('transitResultsToolbar',false);
    el('routeCard')?.classList.add('transit-active');
    el('startNavBtn').disabled=true;
    setRoutePlanningActive(true);
  }
  function armTransitSearchWatchdog(id){
    stopTransitSearchWatchdog();transitSearchRequest=id;
    // Native deadline is 18.5 s; this UI fallback catches bridge failures too.
    transitSearchTimer=setTimeout(()=>{
      if(transitSearchRequest!==id||routeRequestId!==id||mode!=='transit')return;
      const hadResults=!!routeResponse?.routes?.length;
      stopTransitSearchWatchdog();
      const invalidated=++routeRequestId; native()?.cancelRouteRequests?.(invalidated);
      finishRouteCalculationUi();
      if(!hadResults) showTransitSearchFailure('No complete journey was found within 20 seconds. You can retry after timetable preparation finishes.');
    },19_500);
  }
  function cancelActiveRouteRequest(resetUi=true){
    stopTransitSearchWatchdog();
    const invalidId=++routeRequestId;pendingDirections=false;native()?.cancelRouteRequests?.(invalidId);if(resetUi)finishRouteCalculationUi();return invalidId;
  }

  function setDestination(lat, lon, label, address='', meta=null, options={}) {
    cancelActiveRouteRequest(false);
    const preserveMode=!!options.preserveMode||!!options.calculate;
    if(!preserveMode&&mode!=='drive')setMode('drive',false);
    if(!options.preserveStops)transitViaStops=[];
    if(!options.preserveOrigin&&options.resetOrigin)originOverride=null;
    destination = {lat:Number(lat),lon:Number(lon)};
    destinationLabel = label || 'Destination';
    destinationAddress = address || '';
    destinationMeta = meta;
    routeResponse = null;
    selectedRoute = 0; selectedRouteId='';routeSelectionUserMade=false;
    clearRouteLayers();
    renderDestinationMarker();
    el('selectedDestinationName').textContent = destinationLabel;
    el('selectedDestinationAddress').textContent = destinationAddress;
    renderDestinationMeta();
    updateStarButton();
    el('destinationName').textContent = destinationLabel;
    hideSearchDropdown(); hideStarMenu();
    show('routeCard', false);
    show('destinationCard', !options.calculate);
    setRoutePlanningActive(!!options.calculate);renderRoutePlanner();
    native()?.prepareTransitDestination?.(Number(lat),Number(lon));
    if(options.calculate){calculateRoute();return;}
    if (map) map.easeTo({center:[Number(lon),Number(lat)],zoom:13.5,duration:550});
  }

  function clearDestination() {
    cancelActiveRouteRequest();
    ++alongRouteRequestId;++busRouteRequestId;++busLiveRequestId;++busStopRequestId;++suggestionRequestId;++searchRequestId;++mapAreaSearchRequestId;
    destination = null; destinationLabel = ''; destinationAddress = ''; destinationMeta = null; pendingDirections = false; originOverride=null;
    clearAreaSearchMarkers(); clearAlongRouteMarkers(); clearBusRouteMarkers();
    routeResponse = null; selectedRoute = 0; selectedRouteId='';
    if (destMarker) { destMarker.remove(); destMarker=null; }
    clearRouteLayers();
    show('destinationCard', false); show('routeCard', false); show('transitDetailSheet',false); show('busServiceSheet',false); hideSearchDropdown(); hideStarMenu();closeRoutePlanner();
    transitViaStops=[]; resetRoutePointSelection(); setRoutePlanningActive(false);el('searchInput').value='';el('searchInput').readOnly=false;el('searchInput').placeholder='Where to?';renderRoutePlanner();
  }

  function requestDirections() {
    if (!destination) return;
    setRoutePlanningActive(true);closeRoutePlanner();
    if (!routeOrigin()) {
      pendingDirections = true; locating = true; el('locateBtn').classList.add('locating');
      toast('Getting your current location…');
      native().requestLocation();
      return;
    }
    pendingDirections = false;
    calculateRoute();
  }

  function calculateRoute() {
    if (!destination) return;
    const origin=routeOrigin();if(!origin)return requestDirections();
    hideSearchDropdown();
    el('directionsBtn').disabled = true;
    const directionsLabel=el('directionsBtn')?.querySelector('span'); if(directionsLabel) directionsLabel.textContent='Calculating…';
    el('startNavBtn').disabled = true;
    el('startNavBtn').textContent = 'Updating…';
    const id=++routeRequestId;native()?.cancelRouteRequests?.(id);
    stopTransitSearchWatchdog();
    if(mode==='transit')armTransitSearchWatchdog(id);
    closeRoutePlanner();
    const settings=JSON.stringify({...transitPreferences,maxWalk:999,ranking:transitPreference,resultLimit:TRANSIT_RESULT_LIMIT});
    if(mode==='transit'){
      if(el('routeOptions')) el('routeOptions').innerHTML='<div class="transit-loading"><strong>Finding public transport…</strong><span>Timetable routes first; live positions will follow.</span></div>';
      if(origin.custom&&native()?.calculateTransitRouteWithStopsFrom)native().calculateTransitRouteWithStopsFrom(origin.lat,origin.lon,destination.lat,destination.lon,JSON.stringify(transitViaStops),settings,id);
      else native()?.calculateTransitRouteWithStops?.(destination.lat,destination.lon,JSON.stringify(transitViaStops),settings,id);
    } else if(transitViaStops.length){
      if(mode==='drive'&&native()?.calculateRouteWithStops){
        const stops=JSON.stringify(transitViaStops);
        if(origin.custom&&native()?.calculateRouteWithStopsFrom)native().calculateRouteWithStopsFrom(origin.lat,origin.lon,destination.lat,destination.lon,stops,mode,id);
        else native().calculateRouteWithStops(destination.lat,destination.lon,stops,mode,id);
      }else{
        const via=transitViaStops[0];
        if(origin.custom&&native()?.calculateRouteViaStopFrom)native().calculateRouteViaStopFrom(origin.lat,origin.lon,destination.lat,destination.lon,Number(via.lat),Number(via.lon),mode,id);
        else native()?.calculateRouteViaStop?.(destination.lat,destination.lon,Number(via.lat),Number(via.lon),mode,id);
      }
    } else if(origin.custom&&native()?.calculateRouteFrom)native().calculateRouteFrom(origin.lat,origin.lon,destination.lat,destination.lon,mode,id);
    else native()?.calculateRoute?.(destination.lat,destination.lon,mode,id);
  }

  function finishRouteCalculationUi() {
    el('directionsBtn').disabled = false;
    const directionsLabel=el('directionsBtn')?.querySelector('span'); if(directionsLabel) directionsLabel.textContent='Directions';
    el('startNavBtn').disabled = false;
    el('startNavBtn').textContent = 'Start';
  }

  function clearRouteLayers() {
    transitStopData.clear();
    routeLabelMarkers.forEach(marker=>{ try{marker.remove();}catch(_){} }); routeLabelMarkers=[];
    // Remove every MapLibre route/stop layer first, then its GeoJSON source. Keeping both
    // the route line and stop dots inside MapLibre prevents DOM marker drift while zooming.
    routeLayerIds.filter(id=>!id.startsWith('route-src-')).forEach(id=>{ if(map?.getLayer(id)) map.removeLayer(id); });
    routeLayerIds.filter(id=>id.startsWith('route-src-')).forEach(id=>{ if(map?.getSource(id)) map.removeSource(id); });
    routeLayerIds=[];
  }

  function transitOverlayGeometrySignature(data=routeResponse,selectedIndex=selectedRoute){
    if(!data?.routes?.length)return '';
    const compact=data.routes.slice(0,9).map(route=>[
      route?.clearRouteId||'',
      (route?.legs||[]).map(leg=>(leg?.points||[]).map(p=>[Number(Number(p?.longitude).toFixed(6)),Number(Number(p?.latitude).toFixed(6))])),
      (route?.transitLegs||[]).map(leg=>(leg?.stops||[]).map(stop=>[String(stop?.id||''),Number(Number(stop?.lon).toFixed(6)),Number(Number(stop?.lat).toFixed(6))]))
    ]);
    return `${selectedIndex}|${JSON.stringify(compact)}`;
  }

  function routeCoordinates(route) {
    const coords=[];
    (route.legs||[]).forEach(leg => (leg.points||[]).forEach(p => {
      const c=[p.longitude,p.latitude];
      if(!coords.length || coords[coords.length-1][0]!==c[0] || coords[coords.length-1][1]!==c[1]) coords.push(c);
    }));
    return coords;
  }

  function selectRoute(index, fit=true) {
    if(!routeResponse?.routes?.[index]) return;
    selectedRoute=index;selectedRouteId=routeResponse.routes[index]?.clearRouteId||'';routeSelectionUserMade=true;closeRoutePlanner();
    populateRouteOptions();updateRoutePlannerSummary();
    drawRoutes(navigating);
    if(fit && !navigating) fitSelectedRoute();
  }

  function fitSelectedRoute() {
    if(!map || !routeResponse?.routes?.[selectedRoute]) return;
    const coords=routeCoordinates(routeResponse.routes[selectedRoute]);
    if(coords.length<2) return;
    const b=coords.reduce((bounds,c)=>bounds.extend(c),new maplibregl.LngLatBounds(coords[0],coords[0]));
    const bottom=el('routeCard')?.classList.contains('hidden') ? 180 : 330;
    map.fitBounds(b,{padding:{top:120,bottom,left:45,right:45},duration:650,maxZoom:16.5});
  }

  // Keep transit geometry bounded to the boarded segment, even when a provider
  // returns the entire service. Project stop coordinates onto the line rather
  // than just snapping to an arbitrary vertex.
  function clipTransitLegGeometry(points,leg){
    if(points.length<2||!leg)return points;
    const stops=Array.isArray(leg.stops)?leg.stops.filter(p=>Number.isFinite(Number(p.lat))&&Number.isFinite(Number(p.lon))):[];
    const first=stops[0],last=stops[stops.length-1];
    const coord=(provided,backup)=>provided!=null&&Number.isFinite(Number(provided))?Number(provided):Number(backup);
    const board=[coord(leg.fromLon,first?.lon),coord(leg.fromLat,first?.lat)];
    const alight=[coord(leg.toLon,last?.lon),coord(leg.toLat,last?.lat)];
    if(!board.every(Number.isFinite)||!alight.every(Number.isFinite))return points;
    const nearest=target=>{
      let best={distance:Infinity,index:0,t:0,point:target};
      for(let i=0;i<points.length-1;i++){
        const a=points[i],b=points[i+1],scale=Math.cos(target[1]*Math.PI/180),dx=(b[0]-a[0])*scale,dy=b[1]-a[1];
        const len=dx*dx+dy*dy,t=len?Math.max(0,Math.min(1,((target[0]-a[0])*scale*dx+(target[1]-a[1])*dy)/len)):0;
        const p=[a[0]+(b[0]-a[0])*t,a[1]+(b[1]-a[1])*t];
        const d=(p[0]-target[0])**2*scale**2+(p[1]-target[1])**2;
        if(d<best.distance)best={distance:d,index:i,t,point:p};
      }
      return best;
    };
    const a=nearest(board),b=nearest(alight);
    // A mismatch indicates service-level or reversed geometry; a direct
    // segment is safer than showing service sections before boarding.
    if(a.distance>0.00003||b.distance>0.00003||a.index+a.t>=b.index+b.t)
      return [board,alight];
    return [board,...points.slice(a.index+1,b.index+1),alight];
  }
  function desaturateTransitJourney(){
    if(!map||!routeResponse?.routes)return;
    routeResponse.routes.forEach((route,i)=>(route.transitLegs||[]).forEach((leg,li)=>{
      const id=`route-line-${i}-${li}`;
      if(!map.getLayer(id))return;
      const hex=transitLegColour(route,li,i===selectedRoute);
      const rgb=[1,3,5].map(n=>parseInt(hex.slice(n,n+2),16)),gray=Math.round(rgb[0]*.2126+rgb[1]*.7152+rgb[2]*.0722);
      const toHex=n=>Math.round(n).toString(16).padStart(2,'0');
      const muted='#'+rgb.map(v=>toHex((v+gray)/2)).join('');
      map.setPaintProperty(id,'line-color',muted);
      map.setPaintProperty(id,'line-opacity',.55);
    }));
  }

  function drawRoutes(navigationOnly=navigating, fitCamera=false) {
    if (!map?.isStyleLoaded() || !routeResponse?.routes) return;
    clearRouteLayers();
    const visible=new Set(navigationOnly?[selectedRoute]:visibleRouteIndices());
    const order=routeResponse.routes.map((_,i)=>i).filter(i=>visible.has(i)).sort((a,b)=>(a===selectedRoute?1:0)-(b===selectedRoute?1:0));
    order.forEach(i => {
      const route=routeResponse.routes[i];
      if(navigationOnly && i!==selectedRoute) return;
      const selected=i===selectedRoute;
      if(route.clearRouteTransit && Array.isArray(route.legs) && route.legs.length){
        const transitLegs=Array.isArray(route.transitLegs)?route.transitLegs:[];
        route.legs.forEach((leg,li)=>{
          const pts=clipTransitLegGeometry((leg?.points||[]).map(p=>[Number(p.longitude),Number(p.latitude)]).filter(c=>Number.isFinite(c[0])&&Number.isFinite(c[1])),transitLegs[li]);
          if(pts.length<2)return;
          const modeName=transitLegs[li]?.mode||'transit';
          const source=`route-src-${i}-${li}`, casing=`route-case-${i}-${li}`, line=`route-line-${i}-${li}`, hit=`route-hit-${i}-${li}`;
          routeLayerIds.push(casing,line,hit,source);
          map.addSource(source,{type:'geojson',data:{type:'Feature',properties:{routeIndex:i,legIndex:li},geometry:{type:'LineString',coordinates:pts}}});
          map.addLayer({id:casing,type:'line',source,layout:{'line-join':'round','line-cap':'round'},paint:{'line-color':'#ffffff','line-width':selected?8:6.5,'line-opacity':selected?.92:.58}});
          map.addLayer({id:line,type:'line',source,layout:{'line-join':'round','line-cap':'round'},paint:{'line-color':transitLegColour(route,li,selected),'line-width':selected?5.7:4.1,'line-opacity':selected?.98:.72}});
          if(!navigationOnly){
            map.addLayer({id:hit,type:'line',source,layout:{'line-join':'round','line-cap':'round'},paint:{'line-color':'#000000','line-width':20,'line-opacity':0}});
          }
        });
      } else {
        const coords=routeCoordinates(route); if(coords.length<2) return;
        const source=`route-src-${i}`, casing=`route-case-${i}`, line=`route-line-${i}`, hit=`route-hit-${i}`;
        routeLayerIds.push(casing,line,hit,source);
        map.addSource(source,{type:'geojson',data:{type:'Feature',properties:{routeIndex:i},geometry:{type:'LineString',coordinates:coords}}});
        map.addLayer({id:casing,type:'line',source,layout:{'line-join':'round','line-cap':'round'},paint:{'line-color':'#ffffff','line-width':selected?10:8,'line-opacity':selected?.96:.82}});
        map.addLayer({id:line,type:'line',source,layout:{'line-join':'round','line-cap':'round'},paint:{'line-color':selected?'#1a73e8':'#9aa0a6','line-width':selected?7:5,'line-opacity':selected?.98:.9}});
        if(!navigationOnly) {
          map.addLayer({id:hit,type:'line',source,layout:{'line-join':'round','line-cap':'round'},paint:{'line-color':'#000000','line-width':22,'line-opacity':0}});
          const middle=coords[Math.floor(coords.length/2)];
          if(middle){
            const badge=document.createElement('button'); badge.className='route-map-badge'+(selected?' selected':'');
            badge.textContent=formatTime(Number(route.summary?.travelTimeInSeconds)||0);
            badge.onclick=e=>{e.stopPropagation();selectRoute(i,true);};
            routeLabelMarkers.push(new maplibregl.Marker({element:badge,anchor:'center'}).setLngLat(middle).addTo(map));
          }
        }
      }
    });
    if(!navigationOnly){renderTransitStopLayer(routeResponse.routes[selectedRoute]);if(fitCamera)fitSelectedRoute();}
    if(mode==='transit'){transitOverlaySignature=transitOverlayGeometrySignature(routeResponse,selectedRoute);pendingTransitOverlayRefresh=false;}
  }

  function bearingTo(lat1,lon1,lat2,lon2){const p1=lat1*Math.PI/180,p2=lat2*Math.PI/180,dl=(lon2-lon1)*Math.PI/180;return (Math.atan2(Math.sin(dl)*Math.cos(p2),Math.cos(p1)*Math.sin(p2)-Math.sin(p1)*Math.cos(p2)*Math.cos(dl))*180/Math.PI+360)%360;}
  function angleDifference(a,b){let d=Math.abs(a-b)%360;return d>180?360-d:d;}
  function openBusStop(stop){
    const lat=Number(stop?.lat),lon=Number(stop?.lon);if(!Number.isFinite(lat)||!Number.isFinite(lon))return;
    busStopReturnSheet=el('busServiceSheet')&&!el('busServiceSheet').classList.contains('hidden')?'busServiceSheet':(el('transitDetailSheet')&&!el('transitDetailSheet').classList.contains('hidden')?'transitDetailSheet':'routeCard');
    show(busStopReturnSheet,false);
    busStopData={stop:{id:stop.id||'',name:stop.name||'Bus stop',lat,lon},services:[]};el('busStopTitle').textContent=stop.name||'Bus stop';el('busStopSource').textContent='Loading services…';el('busStopServices').innerHTML='<div class="transit-loading"><strong>Loading this stop…</strong></div>';show('busStopSheet');el('busStopSheet').classList.remove('minimised');
    const id=++busStopRequestId;native()?.lookupBusStop?.(String(stop.id||''),lat,lon,id);
  }
  function renderTransitStopLayer(route){
    transitStopData.clear();if(!map||navigating||!route?.transitLegs)return;
    const seen=new Set(),features=[];(route.transitLegs||[]).forEach((leg,li)=>{const m=normaliseTransitMode(leg.mode);if(!['bus','coach'].includes(m))return;const stops=Array.isArray(leg.stops)?leg.stops:[];stops.forEach((stop,idx)=>{const lat=Number(stop.lat),lon=Number(stop.lon);if(!Number.isFinite(lat)||!Number.isFinite(lon))return;const identity=String(stop.id||`${lat.toFixed(6)},${lon.toFixed(6)}`),key=`${identity}|${lat.toFixed(6)}|${lon.toFixed(6)}`;if(seen.has(key))return;seen.add(key);transitStopData.set(key,stop);const bearing=stopTravelBearing(stops,idx),properties={stopKey:key,transfer:(idx===0||idx===stops.length-1)?1:0,stopColor:transitLegColour(route,li)};if(bearing!==null)properties.bearing=bearing;features.push({type:'Feature',properties,geometry:{type:'Point',coordinates:[lon,lat]}});});});
    if(!features.length)return;
    const source='route-src-transit-stops',dots='route-transit-stop-dots',direction='route-transit-stop-direction',hit='route-transit-stop-hit';routeLayerIds.push(dots,direction,hit,source);
    map.addSource(source,{type:'geojson',data:{type:'FeatureCollection',features}});
    map.addLayer({id:dots,type:'circle',source,paint:{'circle-radius':['case',['==',['get','transfer'],1],8,7],'circle-color':['get','stopColor'],'circle-stroke-color':'#ffffff','circle-stroke-width':2,'circle-opacity':1}});
    const icon=addStopDirectionIcon();if(icon)map.addLayer({id:direction,type:'symbol',source,filter:['has','bearing'],layout:{'icon-image':icon,'icon-size':.85,'icon-rotate':['get','bearing'],'icon-rotation-alignment':'map','icon-allow-overlap':true,'icon-ignore-placement':true}});
    map.addLayer({id:hit,type:'circle',source,paint:{'circle-radius':16,'circle-color':'#000000','circle-opacity':0}});
  }
  function renderBusStopSheet(data){
    busStopData=data||busStopData||{};const stop=busStopData.stop||{},box=el('busStopServices');el('busStopTitle').textContent=stop.name||'Bus stop';el('busStopSource').textContent=busStopData.source||'Official timetable';box.textContent='';const services=Array.isArray(busStopData.services)?busStopData.services:[];
    if(!services.length){box.innerHTML='<div class="bus-about">No upcoming buses were found at this stop.</div>';return;}
    services.slice(0,24).forEach(svc=>{const b=document.createElement('button');b.type='button';b.className='bus-stop-service';const line=document.createElement('span');line.className='bus-stop-service-line';line.textContent=svc.line||'Bus';const copy=document.createElement('span');copy.className='bus-stop-service-copy';const strong=document.createElement('strong');strong.textContent=svc.destination||`Bus ${svc.line||''}`;const small=document.createElement('small');small.textContent=(svc.departures||[]).slice(1,3).join(' · ')||'Tap for route';copy.append(strong,small);const next=document.createElement('span');next.className='bus-stop-service-next';next.textContent=(svc.departures||[])[0]||'Route';b.append(line,copy,next);b.onclick=()=>{show('busStopSheet',false);openBusService({line:svc.line,fromAtco:stop.id||'',fromLat:Number(stop.lat),fromLon:Number(stop.lon),from:stop.name||'Bus stop'},'busStopSheet');};box.appendChild(b);});
  }

  function openBusService(leg,returnTo=null){
    if(!leg?.line)return;
    ++busLiveRequestId;const tl=Number(leg.fromLat),tn=Number(leg.fromLon);busServiceTargetStop=Number.isFinite(tl)&&Number.isFinite(tn)?{id:leg.fromAtco||leg.fromStopId||'',name:leg.from||'Boarding stop',lat:tl,lon:tn}:null;
    busServiceReturnSheet=returnTo||(el('transitDetailSheet')&&!el('transitDetailSheet').classList.contains('hidden')?'transitDetailSheet':'routeCard');
    show('transitDetailSheet',false);show('busStopSheet',false);show('routeCard',false);
    const lat=Number(leg.fromLat),lon=Number(leg.fromLon);const id=++busRouteRequestId;
    toast(`Loading bus ${leg.line}…`);
    if(Number.isFinite(lat)&&Number.isFinite(lon)&&native()?.lookupBusRouteNear)native().lookupBusRouteNear(String(leg.line),lat,lon,id);
    else native()?.lookupBusRoute?.(String(leg.line),id);
  }

  function makeTransitStage(leg,route,index){
    const modeKey=normaliseTransitMode(leg?.mode),linked=(modeKey==='bus'||modeKey==='coach')&&!!leg?.line;
    const node=document.createElement(linked?'button':'span');if(linked)node.type='button';node.className=`transit-stage mode-${modeKey}${linked?' linked':''}`;
    const icon=document.createElement('span');icon.className='stage-icon';icon.textContent=transitModeIcon(modeKey);
    if(['bus','coach'].includes(modeKey))node.style.background=transitLegColour(route,index);
    const copy=document.createElement('span');copy.className='stage-copy';const title=document.createElement('span');title.textContent=modeKey==='foot'?'Walk':`${transitModeLabel(modeKey)}${leg?.line?` ${leg.line}`:''}`;copy.appendChild(title);
    const mins=transitLegMinutes(leg);if(mins){const small=document.createElement('small');small.textContent=`${mins} min`;copy.appendChild(small);}node.append(icon,copy);
    if(linked)node.onclick=e=>{e.stopPropagation();openBusService(leg);};return node;
  }

  function showTransitDetail(index){
    const route=routeResponse?.routes?.[index];if(!route)return;selectRoute(index,false);
    const s=route.summary||{};el('transitDetailTitle').textContent=`${route.clearRouteDeparture||''}${route.clearRouteArrival?` → ${route.clearRouteArrival}`:''}`.trim()||'Journey details';
    el('transitDetailMeta').textContent=`${formatTime(Number(s.travelTimeInSeconds)||0)} · ${transitChanges(route)} ${transitChanges(route)===1?'change':'changes'} · ${route.clearRouteDataStatus==='live'?'Live':route.clearRouteDataStatus==='mixed'?'Mixed live/scheduled':'Scheduled'}`;
    const box=el('transitDetailLegs');box.textContent='';(route.transitLegs||[]).forEach((leg,li)=>{
      const modeKey=normaliseTransitMode(leg.mode),row=document.createElement('div');row.className='transit-detail-leg';
      const icon=document.createElement('div');icon.className=`transit-detail-mode mode-${modeKey}`;icon.style.background=transitLegColour(route,li);icon.textContent=transitModeIcon(modeKey);
      const main=document.createElement('div');main.className='transit-detail-main';const heading=document.createElement('strong');
      if((modeKey==='bus'||modeKey==='coach')&&leg.line){const link=document.createElement('button');link.type='button';link.className='transit-service-link';link.textContent=`${transitModeLabel(modeKey)} ${leg.line}`;link.onclick=()=>openBusService(leg);heading.appendChild(link);}else heading.textContent=modeKey==='foot'?'Walk':`${transitModeLabel(modeKey)}${leg.line?` ${leg.line}`:''}`;
      const detail=document.createElement('small');const bits=[];if(leg.from)bits.push(leg.from);if(leg.to)bits.push(`→ ${leg.to}`);if(leg.stopCount)bits.push(`${leg.stopCount} stops`);if(leg.platform)bits.push(`Platform ${leg.platform}`);if(leg.cancelled)bits.push('Cancelled');detail.textContent=bits.join(' · ');
      const quality=document.createElement('small');quality.textContent=`${leg.timeStatus==='live'?'Live':'Scheduled'}${leg.dataSource?` · ${leg.dataSource}`:''}${leg.liveNote?` · ${leg.liveNote}`:''}`;main.append(heading,detail,quality);
      if(modeKey==='train' && isIndexedTrain(leg)){
        const key=trainKey(leg),actions=document.createElement('div');actions.className='rail-leg-actions';
        const button=document.createElement('button');button.type='button';button.className='rail-live-check';
        button.textContent=expandedTrainTimetable===key?'Hide timetable':'Timetable';
        button.onclick=()=>{
          expandedTrainTimetable=expandedTrainTimetable===key?'':key;
          if(expandedTrainTimetable)requestSelectedTrainDetails(index,li);
          showTransitDetail(index);
        };
        actions.appendChild(button);
        const live=document.createElement('span');live.className='rail-live-inline';
        const status=trainLiveCache.get(key);
        if(status?.matched){
          live.textContent=status.cancelled?'Cancelled':
              (status.delayMinutes>0?'Delayed '+status.delayMinutes+' min':'On time')+
              (status.platform?' · Platform '+status.platform:'');
        }else if(trainLivePending.size&&[...trainLivePending.values()].some(x=>x.key===key)){
          const spinner=document.createElement('span');spinner.className='rail-inline-spinner';live.appendChild(spinner);
          live.appendChild(document.createTextNode('Checking live train…'));
        }else live.textContent=status?.message||'Scheduled · live info loading separately';
        actions.appendChild(live);main.appendChild(actions);
        if(expandedTrainTimetable===key)showTrainTimetableList(main,leg);
      }
      const time=document.createElement('div');time.className='transit-detail-time';time.textContent=`${leg.liveDeparture||leg.departure||''}${leg.arrival?`
${leg.arrival}`:''}`;row.append(icon,main,time);box.appendChild(row);
    });
    show('routeCard',false);show('busServiceSheet',false);show('busStopSheet',false);
    show('transitDetailSheet');el('transitDetailSheet').classList.remove('minimised');
    // Transport results are already displayed; enrichment is independent.
    requestSelectedTrainDetails(index);
  }

  function populateRouteOptions() {
    const box=el('routeOptions'); box.textContent='';
    const routes=routeResponse?.routes||[];
    box.classList.toggle('transit-results',mode==='transit');
    show('transitResultsToolbar',mode==='transit'&&routes.length>0);
    el('routeCard')?.classList.toggle('transit-active',mode==='transit');
    if(mode==='transit'){
      const ids=transitDisplayIndices();
      document.querySelectorAll('.transit-ranking button').forEach(b=>b.classList.toggle('active',b.dataset.rank===transitPreference));
      if(!ids.length){const empty=document.createElement('div');empty.className='transit-empty-results';empty.textContent='No displayed journey uses only the transport types you selected. Re-enable a mode or run a fresh search for more alternatives.';box.appendChild(empty);return;}
      if(!ids.includes(selectedRoute)){selectedRoute=ids[0];selectedRouteId=routes[selectedRoute]?.clearRouteId||'';}
      ids.forEach(i=>{
        const route=routes[i],s=route.summary||{},btn=document.createElement('div');btn.className='route-option transit-route'+(i===selectedRoute?' selected':'');btn.setAttribute('role','button');btn.tabIndex=0;
        const top=document.createElement('div');top.className='transit-card-top';const times=document.createElement('div');times.className='transit-card-times';times.textContent=`${route.clearRouteDeparture||'—'}  →  ${route.clearRouteArrival||'—'}`;const dur=document.createElement('div');dur.className='transit-card-duration';dur.textContent=formatTime(Number(s.travelTimeInSeconds)||0);top.append(times,dur);btn.appendChild(top);
        const info=document.createElement('button');info.type='button';info.className='transit-card-info';info.textContent='i';info.setAttribute('aria-label','More information about this journey');info.onclick=e=>{e.stopPropagation();showTransitDetail(i);};btn.appendChild(info);
        const strip=document.createElement('div');strip.className='transit-stage-strip';(route.transitLegs||[]).forEach((leg,li)=>{if(li){const arrow=document.createElement('span');arrow.className='transit-stage-arrow';arrow.textContent='›';strip.appendChild(arrow);}strip.appendChild(makeTransitStage(leg,route,li));});btn.appendChild(strip);
        const footer=document.createElement('div');footer.className='transit-card-footer';const changes=transitChanges(route),c=document.createElement('span');c.textContent=`${changes} ${changes===1?'change':'changes'}`;footer.appendChild(c);const status=document.createElement('span');const st=(route.clearRouteDataStatus||'scheduled').toLowerCase();status.className=st==='live'?'transit-status-live':st==='mixed'?'transit-status-mixed':'';status.textContent=st==='live'?'● Live':st==='mixed'?'◐ Mixed live/scheduled':'◷ Scheduled';footer.appendChild(status);const loading=transitLoadingText(route);if(loading){const wait=document.createElement('span');wait.className='transit-card-loading';wait.textContent=loading;footer.appendChild(wait);}btn.appendChild(footer);
        if(route.clearRouteWarning){const w=document.createElement('div');w.className='transit-card-note';w.textContent=route.clearRouteWarning;btn.appendChild(w);}btn.onclick=()=>selectRoute(i,true);btn.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();selectRoute(i,true);}};box.appendChild(btn);
      });
      return;
    }
    standardDisplayIndices().forEach(i=>{
      const route=routes[i],s=route.summary||{};
      const btn=document.createElement('button'); btn.className='route-option'+(i===selectedRoute?' selected':'');
      const label=document.createElement('div'); label.className='route-label'; label.textContent=route.clearRouteLabel || (i===0?'Recommended':'Alternative');
      const t=document.createElement('div'); t.className='route-time'; t.textContent=formatTime(Number(s.travelTimeInSeconds)||0);
      const d=document.createElement('div'); d.className='route-distance';d.textContent=formatDistance(Number(s.lengthInMeters)||0)+(mode==='drive' && Number(s.trafficDelayInSeconds)>0?` • ${Math.round(Number(s.trafficDelayInSeconds)/60)} min traffic`:``);
      btn.append(label,t,d);const via=routeVia(route); if(via){const v=document.createElement('div');v.className='route-via';v.textContent=`via ${via}`;btn.appendChild(v);}if(route.clearRouteWarning){const w=document.createElement('div');w.className='route-warning';w.textContent=route.clearRouteWarning;btn.appendChild(w);}btn.onclick=()=>selectRoute(i,true);box.appendChild(btn);
    });
  }

  function routeInstructions(route) {
    const list=route?.guidance?.instructions;
    return Array.isArray(list) ? list : [];
  }

  function showRouteSteps() {
    const route=routeResponse?.routes?.[selectedRoute]; if(!route) return;
    const summary=route.summary||{};
    el('stepsSummary').textContent=`${routeSummary(route)}${routeVia(route)?` • via ${routeVia(route)}`:''}`;
    const list=el('stepsList'); list.textContent='';
    const transitLegs=route.clearRouteTransit && Array.isArray(route.transitLegs)?route.transitLegs:[];
    const instructions=routeInstructions(route);
    if(transitLegs.length){
      transitLegs.forEach(leg=>{
        const row=document.createElement('div');row.className='step-row';
        const icon=document.createElement('div');icon.className='step-icon';icon.textContent=leg.mode==='bus'?'🚌':leg.mode==='train'?'🚆':leg.mode==='foot'?'↟':'●';
        const wrap=document.createElement('div');wrap.className='step-text';
        const main=document.createElement('div');
        const name=leg.mode==='foot'?'Walk':`${leg.mode==='bus'?'Bus':leg.mode==='train'?'Train':(leg.mode||'Service')}${leg.line?` ${leg.line}`:''}`;
        main.textContent=`${name}${leg.to?` to ${leg.to}`:''}`;
        const quality=document.createElement('div');
        const live=leg.timeStatus==='live';quality.className=`transit-leg-quality${live?' live':''}`;
        const shownTime=live?(leg.liveDeparture||leg.departure):(leg.departure||'');
        if(leg.liveVehicleData && !live) quality.textContent=`Scheduled${shownTime?` · ${shownTime}`:''} · BODS live vehicle position available`;
        else quality.textContent=`${live?'Live':'Scheduled'}${shownTime?` · ${shownTime}`:''}${leg.dataSource?` · ${leg.dataSource}`:''}${leg.cancelled?' · Cancelled':''}`;
        if(leg.platform)quality.textContent+=` · Platform ${leg.platform}`;
        if(leg.liveNote)quality.textContent+=` · ${leg.liveNote}`;
        wrap.append(main,quality);
        const dist=document.createElement('div');dist.className='step-distance';dist.textContent=leg.arrival||'';
        row.append(icon,wrap,dist);list.appendChild(row);
      });
    } else if(!instructions.length){list.innerHTML='<div class="empty-state">Step-by-step preview is not available for this route.</div>';}
    else instructions.forEach((ins,i)=>{
      const next=instructions[i+1];
      const offset=Number(ins.routeOffsetInMeters)||0;
      const nextOffset=Number(next?.routeOffsetInMeters);
      const stepDistance=Number.isFinite(nextOffset)?Math.max(0,nextOffset-offset):0;
      const row=document.createElement('div'); row.className='step-row';
      const icon=document.createElement('div'); icon.className='step-icon'; icon.textContent=navigationSymbol(ins.maneuver||ins.maneuverCode,ins.message||ins.instruction);
      const text=document.createElement('div'); text.className='step-text'; text.textContent=ins.message||ins.instruction||'Continue';
      const dist=document.createElement('div'); dist.className='step-distance'; dist.textContent=stepDistance?formatDistance(stepDistance):'';
      row.append(icon,text,dist); list.appendChild(row);
    });
    show('stepsSheet');
  }

  function doSearch() {
    const q=el('searchInput').value.trim();
    if(q.length<2) return;
    ++suggestionRequestId;
    const id=++searchRequestId;
    renderSearchDropdown(null,'Searching…');
    native().search(q, el('searchBias').checked, id);
  }

  function readHome() {
    try { const raw=native()?.getHome?.() || ''; return raw ? JSON.parse(raw) : null; }
    catch (_) { return null; }
  }

  function readFavourites() {
    try { const raw=native()?.getFavourites?.() || '[]'; const list=JSON.parse(raw); return Array.isArray(list)?list:[]; }
    catch(_) { return []; }
  }

  function refreshHomeUi() {
    home=readHome();
    if(home) {
      el('homeSummary').textContent=home.address || home.name || 'Home';
      show('clearHomeRow', true); show('clearHomeBtn', true); el('setHomeBtn').textContent='Change';
    } else {
      el('homeSummary').textContent='Not set'; show('clearHomeRow', false); show('clearHomeBtn', false); el('setHomeBtn').textContent='Set';
    }
  }

  function goHome() {
    home=readHome();
    if(!home) { toast('Set your Home address in Settings first.'); show('settings'); return; }
    hideSearchDropdown(); clearAreaSearchMarkers(); el('searchInput').value='Home';
    setDestination(home.lat,home.lon,'Home',home.address || home.name || ''); requestDirections();
  }

  function openSavedPlaces(fromSettings=false) {
    savedReturnToSettings=!!fromSettings;
    const list=el('savedPlacesList'); list.textContent='';
    const saved=readFavourites(); home=readHome();
    if(home){
      const row=document.createElement('button'); row.className='saved-place';
      row.innerHTML='<span class="saved-place-icon">⌂</span><span><div class="saved-place-name">Home</div><div class="saved-place-sub"></div></span><span></span>';
      row.querySelector('.saved-place-sub').textContent=home.address||'';
      row.onclick=()=>{show('savedSheet',false); if(fromSettings)show('settings',false); setDestination(home.lat,home.lon,'Home',home.address||'');};
      list.appendChild(row);
    }
    saved.forEach((f,index)=>{
      const row=document.createElement('div'); row.className='saved-place';
      const icon=document.createElement('button'); icon.className='saved-place-icon'; icon.textContent='★';
      const copy=document.createElement('button'); copy.style.cssText='border:0;background:transparent;text-align:left;padding:0;color:inherit';
      copy.innerHTML='<div class="saved-place-name"></div><div class="saved-place-sub">Starred on this phone</div>';
      copy.querySelector('.saved-place-name').textContent=f.name||'Starred place';
      const rename=document.createElement('button'); rename.className='saved-edit'; rename.textContent='Rename'; rename.setAttribute('aria-label','Rename saved place');
      const remove=document.createElement('button'); remove.className='saved-remove'; remove.textContent='×'; remove.setAttribute('aria-label','Remove saved place');
      const choose=()=>{show('savedSheet',false); if(fromSettings)show('settings',false); setDestination(Number(f.lat),Number(f.lon),f.name||'Starred place','');};
      icon.onclick=choose; copy.onclick=choose;
      rename.onclick=()=>openFavouriteNameEditor('Rename starred place',f.name||'Starred place',name=>{native()?.renameFavourite?.(index,name);setTimeout(()=>{openSavedPlaces(fromSettings);if(poiVisible)renderStarredMarkers();},80);});
      remove.onclick=()=>{native()?.removeFavourite?.(index); setTimeout(()=>{openSavedPlaces(fromSettings);if(poiVisible)renderStarredMarkers();},80);};
      row.append(icon,copy,rename,remove); list.appendChild(row);
    });
    if(!home && !saved.length) list.innerHTML='<div class="empty-state">No starred places yet. Select a place on the map and tap Star.</div>';
    show('savedSheet');
  }

  let favouriteNameAction=null;
  function openFavouriteNameEditor(title,value,onSave){
    favouriteNameAction=typeof onSave==='function'?onSave:null;
    el('favouriteNameTitle').textContent=title||'Name starred place';
    el('favouriteNameInput').value=value||'';
    show('favouriteNameSheet');
    setTimeout(()=>{el('favouriteNameInput').focus();el('favouriteNameInput').select();},60);
  }
  function closeFavouriteNameEditor(){favouriteNameAction=null;show('favouriteNameSheet',false);}
  function commitFavouriteName(){
    const name=(el('favouriteNameInput').value||'').trim();
    if(!name){toast('Give this starred place a name.');return;}
    const action=favouriteNameAction; favouriteNameAction=null; show('favouriteNameSheet',false); if(action) action(name);
  }

  function saveCurrentDestination() {
    if(!destination) return;
    const index=favouriteIndexFor(destination.lat,destination.lon);
    if(index>=0){
      native()?.removeFavourite?.(index); toast('Removed from starred places');
      setTimeout(()=>{updateStarButton(); if(poiVisible)renderStarredMarkers();},80);
      return;
    }
    const defaultName=destinationLabel||'Starred place';
    openFavouriteNameEditor('Name starred place',defaultName,name=>{
      native()?.saveFavourite?.(name,destination.lat,destination.lon); toast('Starred on this phone');
      setTimeout(()=>{updateStarButton(); if(poiVisible)renderStarredMarkers();},80);
    });
  }

  function openAlongRouteSearch() {
    if(!navigating) return;
    el('alongRouteResults').textContent='';
    el('alongRouteStatus').textContent='Choose something to find ahead on your current route.';
    show('alongRouteSheet');
  }

  function formatDetour(r) {
    const seconds=Number(r?.detourTime);
    const metres=Number(r?.detourDistance);
    if(Number.isFinite(seconds) && seconds>=0) {
      const mins=Math.max(0,Math.round(seconds/60));
      return mins <= 0 ? 'On route' : `+${mins} min`;
    }
    if(Number.isFinite(metres) && metres>=0) return metres<1000?`+${Math.round(metres/50)*50} m`:`+${(metres/1000).toFixed(1)} km`;
    return '';
  }

  function searchAlongRoute(query) {
    if(!navigating) return;
    const id=++alongRouteRequestId;
    el('alongRouteResults').textContent='';
    el('alongRouteStatus').textContent=`Searching for ${query} along your route…`;
    native()?.searchAlongRoute?.(query,id);
  }

  function renderAlongRouteResults(data) {
    clearAlongRouteMarkers();
    const box=el('alongRouteResults'); box.textContent='';
    const results=Array.isArray(data?.results)?data.results:[];
    if(!results.length){
      box.innerHTML='<div class="along-route-empty">Nothing suitable was found close to the remaining route.</div>';
      return;
    }
    const addStop=(r,label)=>{
      el('alongRouteStatus').textContent=`Adding ${label} to your route…`;
      clearAlongRouteMarkers();
      native()?.addAlongRouteStop?.(Number(r.position.lat),Number(r.position.lon),label);
    };
    results.forEach(r=>{
      if(!r?.position) return;
      const {label,address}=searchResultText(r);
      const category=searchResultCategory(r);
      const row=document.createElement('button'); row.type='button'; row.className='along-route-result';
      const icon=makeResultIcon(r);
      const copy=document.createElement('span'); copy.className='along-route-result-copy';
      const name=document.createElement('strong'); name.textContent=label;
      const sub=document.createElement('small'); sub.textContent=address || category.label;
      copy.append(name,sub);
      const detour=document.createElement('span'); detour.className='along-route-detour'; detour.textContent=formatDetour(r);
      row.append(icon,copy,detour);
      row.onclick=()=>addStop(r,label);
      box.appendChild(row);

      if(map && mapLoaded){
        const node=document.createElement('button'); node.type='button'; node.className='along-route-map-marker';
        const leader=document.createElement('span'); leader.className='along-route-leader'; leader.setAttribute('aria-hidden','true');
        const point=document.createElement('span'); point.className='along-route-point'; point.setAttribute('aria-hidden','true');
        const callout=document.createElement('span'); callout.className='along-route-callout';
        const icon=document.createElement('span'); icon.className='along-route-callout-icon'; icon.textContent=category.symbol||'•'; icon.setAttribute('aria-hidden','true');
        const badge=document.createElement('span'); badge.className='detour-badge'; badge.textContent=formatDetour(r)||'On route';
        callout.append(icon,badge); node.append(leader,callout,point);
        node.title=label; node.setAttribute('aria-label',`${label}, ${badge.textContent}, add to route`);
        node.onclick=e=>{e.stopPropagation();addStop(r,label);};
        try{
          alongRouteMarkers.push(new maplibregl.Marker({element:node,anchor:'center'}).setLngLat([Number(r.position.lon),Number(r.position.lat)]).addTo(map));
        }catch(_){}
      }
    });
    if(alongRouteMarkers.length){
      requestAlongRouteMarkerLayout();
      setTimeout(requestAlongRouteMarkerLayout,80);
      show('alongRouteSheet',false);
      toast('Stops are shown on the map with their added journey time.');
    }
  }

  function doHomeSearch() {
    const q=el('homeSearchInput').value.trim(); if(q.length<2) return;
    show('homeSearchResults'); el('homeSearchResults').textContent='Searching…';
    const id=++homeSearchRequestId; native().searchHome(q, id);
  }

  function renderSearchResults(data, box, onPick) {
    const results=data.results||[]; box.textContent='';
    if(!results.length){box.innerHTML='<div class="empty-state">No results found</div>';return;}
    results.forEach(r=>{
      const btn=document.createElement('button'); btn.className='result';
      const label=r.poi?.name || r.address?.freeformAddress || 'Destination';
      const addressText=r.address?.freeformAddress || '';
      const icon=makeResultIcon(r);
      const name=document.createElement('div'); name.className='result-name'; name.textContent=label;
      const address=document.createElement('div'); address.className='result-address'; address.textContent=addressText;
      btn.append(icon,name,address); btn.onclick=()=>onPick(r,label,addressText); box.appendChild(btn);
    });
  }

  function openRoutePreferences() {
    el('avoidMotorways').checked=!!native()?.isAvoidMotorways?.();
    el('avoidTolls').checked=!!native()?.isAvoidTolls?.();
    el('avoidFerries').checked=!!native()?.isAvoidFerries?.();
    el('preferMotorways').checked=!!native()?.isPreferMotorways?.();
    show('routePreferences');
  }

  function saveRoutePreferences() {
    const avoid=el('avoidMotorways').checked, prefer=el('preferMotorways').checked;
    native()?.setRouteAvoidances?.(avoid,el('avoidTolls').checked,el('avoidFerries').checked,prefer);
    show('routePreferences',false);
    if(destination && routeOrigin() && mode==='drive' && !navigating) calculateRoute();
  }

  function showRouteOverview() {
    if(!navigating) return;
    navigationFollow=false; updateMapActionVisibility(); fitSelectedRoute();
  }

  function updateNavSoundButton() {
    const modeValue=native()?.getNavigationAlertMode?.() || 'voice';
    const button=el('navSoundBtn'); if(!button)return;
    button.textContent=modeValue==='voice'?'🔊':(modeValue==='flash'?'◉':'🔇');
    button.title=modeValue==='voice'?'Voice guidance':(modeValue==='flash'?'Edge-flash guidance':'Guidance muted');
  }

  function cycleNavAlertMode() {
    const currentMode=native()?.getNavigationAlertMode?.() || 'voice';
    const next=currentMode==='voice'?'flash':(currentMode==='flash'?'silent':'voice');
    native()?.setNavigationAlertMode?.(next); el('navAlertMode').value=next; updateNavSoundButton();
    toast(next==='voice'?'Voice guidance on':(next==='flash'?'Edge-flash guidance':'Guidance muted'));
  }

  function renderUpdateStatus(info){
    const title=el('updateStatusTitle'), detail=el('updateStatusDetail'),install=el('installUpdateBtn'),home=el('updateHomeStatus');
    const installed=el('installedVersionLabel');if(installed)installed.textContent='OpenRoad '+(native()?.getInstalledAppVersion?.()||'0.6.35');
    if(!title||!detail||!install)return;
    const available=['available','downloading','permission','ready'].includes(info?.state);
    title.textContent=available?'OpenRoad '+(info.version||''):(info?.state==='current'?'No newer version':'Not checked yet');
    detail.textContent=info?.message||'The app checks for updates daily when opened.';
    install.classList.toggle('hidden',!['available','error','permission'].includes(info?.state)||!info?.version);
    install.disabled=info?.state==='downloading';
    if(home)home.textContent=available?'New version '+(info.version||'')+' available':'Check for a newer signed OpenRoad release';
    el('updateAvailableCard')?.classList.toggle('update-ready',available);
    if(info?.state==='available')toast('OpenRoad '+(info.version||'')+' is ready to install from Settings > App updates.');
  }
  window.ClearRoute = {
    onUpdateStatus(info) {renderUpdateStatus(info);},
    onLocation(loc) {
      current={lat:loc.lat,lon:loc.lon,accuracy:loc.accuracy||0,bearing:loc.bearing||0,hasBearing:!!loc.hasBearing,speed:loc.speed||0,time:loc.time||0}; locating=false; el('locateBtn').classList.remove('locating');
      const firstFix=!initialLocationCentred && !destination && !routeResponse && !navigating;
      renderUserLocation(firstFix); if(firstFix)initialLocationCentred=true;
      if(transitNavigation)updateTransitNavigation();
      if (pendingDirections && destination) { pendingDirections=false; calculateRoute(); }
    },
    onLocationStatus(status) {
      if (status === 'waiting') { locating=true; el('locateBtn').classList.add('locating'); return; }
      locating=false; el('locateBtn').classList.remove('locating');
      if (status === 'disabled') toast('Phone location is switched off. Turn Location on, then return to OpenRoad.');
      if (status === 'permission-denied') toast('OpenRoad needs location permission to centre the map and calculate routes.');
      if (status === 'timeout') toast('Still waiting for a location fix. Check Location accuracy on the phone or try near a window/outdoors.');
    },
    onRouteNeedsLocation(requestId) {
      if(requestId && requestId!==routeRequestId) return;
      finishRouteCalculationUi(); pendingDirections=true;
      toast('Getting your current location…'); native().requestLocation();
    },
    onSearchResults(data, requestId) {
      if(requestId!==searchRequestId) return;
      renderSearchDropdown(data);
    },
    onSearchSuggestions(data, requestId) {
      if(requestId!==suggestionRequestId) return;
      renderSearchDropdown(data);
    },
    onSearchSuggestionError(requestId,message) {
      if(requestId!==suggestionRequestId) return;
      renderSearchDropdown(null,message || 'Suggestions unavailable');
    },
    onMapAreaSearchResults(data, requestId) {
      if(placeCategoryRequests.has(requestId)){const category=placeCategoryRequests.get(requestId);placeCategoryRequests.delete(requestId);renderPlaceCategoryResults(category,data);return;}
      if(requestId!==mapAreaSearchRequestId) return;
      showAreaSearchResults(data);
    },
    onMapAreaSearchError(requestId,message) {
      if(placeCategoryRequests.has(requestId)){const category=placeCategoryRequests.get(requestId);placeCategoryRequests.delete(requestId);clearPlaceCategoryMarkers(category);return;}
      if(requestId!==mapAreaSearchRequestId) return;
      toast(message || 'Could not search this map area');
    },
    onHomeSearchResults(data, requestId) {
      if(requestId!==homeSearchRequestId) return;
      const box=el('homeSearchResults');
      renderSearchResults(data, box, (r,label,addressText)=>{
        native().saveHome('Home', addressText || label, r.position.lat, r.position.lon);
      });
    },
    onSearchError(requestId,message){ if(requestId===searchRequestId) renderSearchDropdown(null,message||'Search failed'); },
    onHomeSearchError(requestId,message) { if(requestId===homeSearchRequestId) el('homeSearchResults').textContent=message || 'Home search failed'; },
    onHomeSaved(savedHome) {
      home=savedHome; refreshHomeUi(); show('homeSetup',false); show('settings',true);showSettingsPage('places');
      el('homeSearchInput').value=''; show('homeSearchResults',false); toast('Home saved');
    },
    onHomeCleared() { home=null; refreshHomeUi(); toast('Home cleared'); },
    onRoute(data, requestedIndex=0, restored=false, requestId=0) {
      if(!restored && requestId && requestId!==routeRequestId) return;
      stopTransitSearchWatchdog();
      finishRouteCalculationUi(); routeResponse=data; routeSelectionUserMade=false;selectedRoute=Math.min(requestedIndex,Math.max(0,(data.routes||[]).length-1));selectedRouteId=data.routes?.[selectedRoute]?.clearRouteId||selectedRouteId||'';
      if(!data.routes?.length){toast('No route found');return;}
      if(!destination) {
        const points=routeCoordinates(data.routes[selectedRoute]); const last=points[points.length-1];
        if(last){destination={lon:last[0],lat:last[1]}; destinationLabel='Destination';}
      }
      if(restored) { navigating=true; navigationFollow=true; angledView=true; updateViewButtons(); }
      el('destinationName').textContent = destinationLabel || 'Destination';
      populateRouteOptions(); drawRoutes(navigating,!navigating);
      el('startNavBtn').textContent='Start';
      show('destinationCard', false); hideSearchDropdown(); show('routeCard',!navigating);
      closeRoutePlanner();show('transitResultsToolbar',mode==='transit'&&!navigating);
      el('routeCard')?.classList.toggle('transit-active',mode==='transit');renderRoutePlanner();setRoutePlanningActive(!navigating);
      if(restored) { setNavigationChrome(true); updateNavSoundButton(); }
      if(mode==='transit'&&!restored)requestSelectedTrainDetails(selectedRoute);
    },
    onRouteLiveUpdate(data, requestId=0){
      if(requestId && requestId!==routeRequestId) return;
      if(mode!=='transit' || !data?.routes?.length) return;
      const previousId=selectedRouteId||routeResponse?.routes?.[selectedRoute]?.clearRouteId||'';
      // Never silently switch journeys when late data arrives.
      if(previousId&&!data.routes.some(r=>r?.clearRouteId===previousId))return;
      routeResponse=data;
      routeResponse.routes?.forEach(applyTrainDetailsFromCache);
      let keep=-1;if(previousId)keep=data.routes.findIndex(r=>r?.clearRouteId===previousId);if(keep<0)keep=Math.min(selectedRoute,Math.max(0,data.routes.length-1));selectedRoute=keep;selectedRouteId=data.routes?.[selectedRoute]?.clearRouteId||previousId;
      const allowed=transitDisplayIndices();if(allowed.length&&!allowed.includes(selectedRoute)){selectedRoute=allowed[0];selectedRouteId=data.routes?.[selectedRoute]?.clearRouteId||'';}
      if(transitNavigation)transitNavigation.routeIndex=selectedRoute;populateRouteOptions();updateRoutePlannerSummary();
      const nextOverlay=transitOverlayGeometrySignature(data,selectedRoute);
      if(nextOverlay!==transitOverlaySignature){if(map?.isMoving?.()){pendingTransitOverlayRefresh=true;}else drawRoutes(navigating,false);}
    },
    onTransitSearchProgress(requestId,stage,elapsedMs){
      if(requestId!==routeRequestId||transitSearchRequest!==requestId)return;
      const label=el('routeOptions')?.querySelector('.transit-loading span');
      if(label)label.textContent=String(stage||'Searching timetables…')+' · '+Math.min(19,Math.floor(Number(elapsedMs||0)/1000))+'s';
    },
    onRouteError(requestId,message){
      if(requestId!==routeRequestId)return;
      stopTransitSearchWatchdog();
      finishRouteCalculationUi();
      if(mode==='transit')showTransitSearchFailure(message||'No public transport route was found.');
      else toast(message||'Route calculation failed');
    },
    onTransitNavigationRestored(data, requestedIndex=0, legIndex=0){
      routeResponse=data; mode='transit'; selectedRoute=Math.min(requestedIndex,Math.max(0,(data.routes||[]).length-1));selectedRouteId=data.routes?.[selectedRoute]?.clearRouteId||'';
      transitNavigation={routeIndex:selectedRoute,legIndex:Math.max(0,Number(legIndex)||0)};navigating=true;routeSelectionUserMade=true;navigationFollow=true;angledView=false;updateViewButtons();
      populateRouteOptions();drawRoutes(true,false);show('routeCard',false);show('destinationCard',false);closeRoutePlanner();setNavigationChrome(true);el('navUi')?.classList.add('transit-navigation');show('navSpeedPanel',false);show('navAlongRouteBtn',false);show('navOptionsBtn',false);updateTransitNavigation(true);
    },
    onTransitNavigationUpdate(u){
      if(!navigating||mode!=='transit'||!transitNavigation)return;
      current={lat:Number(u.lat),lon:Number(u.lon),bearing:Number(u.bearing)||0,hasBearing:!!u.hasBearing,speed:Number(u.speed)||0,accuracy:current?.accuracy||0};
      transitNavigation.legIndex=Math.max(0,Number(u.legIndex)||0);
      updateTransitNavigation(false);renderUserLocation(false);
      if(navigationFollow)navigationCamera(current.lat,current.lon,current.hasBearing?current.bearing:map.getBearing(),500);
    },

    onNavigationStarted(){
      navigating=true; navigationFollow=true; angledView=true; updateViewButtons(); updateMapActionVisibility();
      show('destinationCard',false); show('routeCard',false); setNavigationChrome(true); drawRoutes(true);
      el('instructionText').textContent='Starting navigation'; el('instructionDistance').textContent=''; el('navManeuverIcon').textContent='↑';
      el('currentSpeed').textContent='0'; el('speedLimit').textContent='—'; el('arrivalTime').textContent='—'; show('navSpeedPanel', mode==='drive'); updateNavSoundButton();
      if(current) navigationCamera(current.lat,current.lon,current.hasBearing?current.bearing:map.getBearing(),600);
    },
    onNavigationStopped(reason='stopped'){
      const wasNavigating=navigating; navigating=false; transitNavigation=null;el('navUi')?.classList.remove('transit-navigation');navigationFollow=true; angledView=false; updateViewButtons(); setNavigationChrome(false);
      map?.easeTo({pitch:0,bearing:0,padding:{top:0,bottom:0,left:0,right:0},duration:450});
      if(reason==='arrived'){ clearDestination(); toast('You have arrived.'); }
      else if(reason==='error'){ toast('Navigation stopped because the active route could not be restored.'); }
      else if(wasNavigating && routeResponse) { drawRoutes(false); show('routeCard'); }
    },
    onNavigationUpdate(u){
      if(!navigating)return;
      current={lat:u.lat,lon:u.lon,bearing:Number(u.bearing)||0,hasBearing:!!u.hasBearing,speed:u.speed||0,accuracy:current?.accuracy||0};
      el('navManeuverIcon').textContent=navigationSymbol(u.maneuver,u.instruction);
      el('instructionText').textContent=u.instruction||'Continue';
      el('instructionDistance').textContent=formatDistance(Number(u.instructionDistance)||0);
      el('remainingTime').textContent=formatTime(Number(u.remainingSeconds)||0);
      el('arrivalTime').textContent=formatArrivalTime(Number(u.remainingSeconds)||0);
      el('remainingDistance').textContent=formatDistance(Number(u.remainingDistance)||0);
      if(mode==='drive') {
        const mph=Math.max(0,Math.round((Number(u.speed)||0)*2.236936));
        const limitKmh=Number(u.speedLimitKmh);
        el('currentSpeed').textContent=String(mph);
        el('speedLimit').textContent=Number.isFinite(limitKmh)&&limitKmh>0 ? String(Math.max(5,Math.round((limitKmh*0.621371)/5)*5)) : '—';
        show('navSpeedPanel',true);
      } else show('navSpeedPanel',false);
      if(u.visualAlert) flashEdges(u.alertPhase||'early');
      renderUserLocation(false);
      if(navigationFollow) navigationCamera(u.lat,u.lon,u.hasBearing?Number(u.bearing):map.getBearing(),650);
    },

    onNavigationStatus(message){
      show('navOptions',false);
      if(message) toast(message);
    },

    onAlongRouteResults(requestId,data){
      if(requestId!==alongRouteRequestId)return;
      el('alongRouteStatus').textContent='Choose a stop to add to your journey.';
      renderAlongRouteResults(data||{});
    },
    onAlongRouteError(requestId,message){
      if(requestId!==alongRouteRequestId)return;
      el('alongRouteStatus').textContent=message||'Could not search along this route.';
      el('alongRouteResults').textContent='';
    },
    onAlongRouteStopAdded(name){
      show('alongRouteSheet',false);
      toast(name ? `${name} added to your route` : 'Stop added to your route');
    },
    onShazamStatus(ok,message){
      if(!ok && message) toast(message);
    },
    onContactsPermission(granted){
      contactsEnabled=!!granted;
      if(el('contactsSearchSummary'))el('contactsSearchSummary').textContent=granted?'Enabled — contacts with postal addresses appear in search':'Permission not granted';
      if(el('contactsSearchAction'))el('contactsSearchAction').textContent=granted?'On':'Enable';
      if(granted){const q=el('searchInput').value.trim();if(q.length>=1)requestSearchSuggestions();if(placeCategories.contacts)refreshPlaceCategories();}
    },
    onContactGeocodeFailed(name,address){
      const key=`${name||'Contact'}|${address||''}`.toLowerCase();
      const background=contactBackgroundGeocodes.has(key);
      contactBackgroundGeocodes.delete(key);
      document.querySelectorAll('.contact-suggestion.loading').forEach(n=>{n.classList.remove('loading');n.disabled=false;});
      if(!background)toast('Could not locate that contact address.');
    },
    onContactGeocoded(name,address,lat,lon){document.querySelectorAll('.contact-suggestion.loading').forEach(n=>{n.classList.remove('loading');n.disabled=false;});
      if(!Number.isFinite(Number(lat))||!Number.isFinite(Number(lon)))return toast('Could not locate that contact address.');
      const entry={name:name||'Contact',address:address||'',lat:Number(lat),lon:Number(lon)};const key=`${entry.name}|${entry.address}`.toLowerCase();contactPlaceCache=contactPlaceCache.filter(c=>`${c.name}|${c.address}`.toLowerCase()!==key);contactPlaceCache.unshift(entry);saveContactPlaceCache();if(placeCategories.contacts)renderContactPlaceMarkers();
      if(contactBackgroundGeocodes.has(key)){contactBackgroundGeocodes.delete(key);return;}
      if(routePointSelectionActive()){applyRoutePointSelection(Number(lat),Number(lon),name||'Contact',address||'',{category:'Contact'});return;}
      el('searchInput').value=name||'Contact';
      setDestination(Number(lat),Number(lon),name||'Contact',address||'',{category:'Contact'});
    },
    onPlaceDetails(data,lat,lon){
      const results=data?.results||[]; if(!results.length||!destination)return;
      const r=results[0], meta=placeMetaFromResult(r);
      destinationMeta=meta;
      const text=searchResultText(r);
      if(text.address)destinationAddress=text.address;
      renderDestinationMeta();
      el('selectedDestinationAddress').textContent=destinationAddress||'';
    },
    onBusStop(data,requestId){if(requestId!==busStopRequestId)return;renderBusStopSheet(data);},
    onBusStopError(requestId,message){if(requestId!==busStopRequestId)return;el('busStopSource').textContent=message||'Could not load this stop.';el('busStopServices').innerHTML='<div class="bus-about">Bus-stop information is unavailable.</div>';},
    onBusRoute(data,requestId){if(requestId!==busRouteRequestId)return;drawBusRoute(data);},
    onBusRouteError(requestId,message){if(requestId!==busRouteRequestId)return;toast(message||'Could not load that bus route.');backFromBusService();},
    onBusLive(data,requestId){if(requestId!==busLiveRequestId||!busServiceData||String(data?.line||'').toLowerCase()!==String(busServiceData.line||'').toLowerCase())return;if(busServiceData){busServiceData.vehicles=Array.isArray(data?.vehicles)?data.vehicles:[];busServiceData.liveStale=data?.coverage==='last-known-vehicles';busServiceData.liveSource=data?.source||'BODS';renderBusLiveMarkers();renderBusServiceContent();}},
    onBusLiveError(requestId,message){if(requestId!==busLiveRequestId)return;const btn=el('loadBusLiveBtn');if(btn){btn.disabled=false;btn.classList.remove('loading');btn.textContent=busServiceTargetStop?'Next 3 live buses':'Live buses';}if(/hourly request limit reached|hourly request budget reached/i.test(String(message||''))){
        const m=String(message||'').match(/(\d+) minutes/i);
        busLiveGlobalRetryUntil=Date.now()+Math.max(1,m?Number(m[1]):10)*60000;
      }
      toast(message||'Live bus positions are unavailable.');},
    onTransitCredentialSaved(provider,ok){
      if(ok){refreshProviderSettings();toast(`${provider==='bods'?'BODS':provider==='tfl'?'TfL':'National Rail'} credentials saved securely.`);}
      else toast('Could not save those public-transport credentials.');
    },
    onRailDepartures(ok,payload){
      const context=railBoardContext;railBoardContext=null;
      if(context){
        const route=routeResponse?.routes?.[context.routeIndex];
        const leg=route?.transitLegs?.[context.legIndex];
        if(!ok){toast('Live train information is unavailable. Scheduled times remain unchanged.');}
        else if(leg && context.crs===String(payload?.station||'').toUpperCase()){
          const services=Array.isArray(payload?.services)?payload.services:[];
          // A station may have multiple trains at the same advertised time.
          // Do not wrongly attach an unrelated prediction or platform.
          const matches=services.filter(x=>x.std===leg.departure);
          if(matches.length===1){
            const match=matches[0],prediction=String(match.etd||'');
            const valid=match.cancelled===true || /^\d{1,2}:\d{2}$/.test(prediction) || /^(on time)$/i.test(prediction);
            if(valid){
              leg.cancelled=match.cancelled===true;
              leg.liveDeparture=leg.cancelled?'Cancelled':(/^\d{1,2}:\d{2}$/.test(prediction)?prediction:leg.departure);
              leg.timeStatus='live';
              leg.platform=match.platform||'';
              leg.dataSource='National Rail live departure board';
              leg.liveNote=leg.cancelled?'Service cancelled':'Last checked against the station departure board';
              route.clearRouteDataStatus='mixed';
            }
          }else leg.liveNote='No unambiguous live match on the current board; scheduled times remain';
          if(context.routeIndex===selectedRoute && !el('transitDetailSheet')?.classList.contains('hidden'))
            showTransitDetail(context.routeIndex);
        }
      }
      const button=el('checkRailDeparturesBtn'), result=el('railDepartureResults');
      button.disabled=false;
      if(!ok){result.textContent=String(payload||'Rail departures unavailable.');result.classList.add('rail-board-error');return;}
      result.classList.remove('rail-board-error');result.textContent='';
      const services=Array.isArray(payload?.services)?payload.services:[];
      const heading=document.createElement('div');heading.className='rail-board-heading';
      heading.textContent=`${payload?.stationName||payload?.station||'Rail station'} · live departure board`;
      result.appendChild(heading);
      if(!services.length){const row=document.createElement('div');row.textContent='No trains listed in the next two hours.';result.appendChild(row);return;}
      services.forEach(service=>{
        const row=document.createElement('div');row.className='rail-board-row';
        const times=document.createElement('strong');
        times.textContent=`${service.std||'—'}${service.cancelled?' · Cancelled':service.etd&&service.etd.toLowerCase()!=='on time'&&service.etd!==service.std?' · '+service.etd:''}`;
        const detail=document.createElement('span');
        detail.textContent=`${service.destination||'Unknown destination'}${service.platform?' · Platform '+service.platform:''}`;
        row.append(times,detail);result.appendChild(row);
      });
    },
    onTransportApiSaved(ok){
      if(ok){refreshProviderSettings(); toast('TransportAPI fallback credentials saved securely.');}
      else toast('Could not save public-transport credentials.');
    },
    onOpenRoadServerPairing(ok,message){
      el('pairOpenRoadServerBtn').disabled=false;
      if(ok){el('openRoadPairingCode').value='';refreshProviderSettings();toast(message||'OpenRoad server paired securely.');}
      else toast(message||'Could not pair with the OpenRoad server.');
    },
    onOpenRoadServerCheck(ok,payload){
      el('checkOpenRoadServerBtn').disabled=false;
      if(!ok){if(el('preparedAreasSummary'))el('preparedAreasSummary').textContent='Private server unavailable';return toast(payload||'Could not reach the OpenRoad server.');}
      try{const s=JSON.parse(payload||'{}');const regions=Array.isArray(s.regions)?s.regions:[];if(el('preparedAreasSummary')){const lines=regions.length?regions.map(r=>`${r.label||r.region_key}${Number(r.permanent)?' · permanent':' · ready'}`):['Bristol / South West · permanent'];el('preparedAreasSummary').textContent=lines.join('  •  ');}toast(s.datasetReady?`Server ready · timetable ${s.datasetUpdated||'updated'}`:'Server paired, but timetable data is not ready yet.');}
      catch(_){toast('OpenRoad server is responding securely.');}
    },
    onOpenRoadServerRemoved(revoked){
      refreshProviderSettings();
      toast(revoked?'This phone was removed from the OpenRoad server.':'Local pairing cleared. If the server was offline, revoke the old device from cPanel before pairing again.');
    },
    onTtsVoices(data){
      const selectedEngine=el('ttsEngineSelect').value || '';
      if((data?.engine||'')!==selectedEngine) return;
      const select=el('ttsVoiceSelect'); select.textContent='';
      const def=document.createElement('option'); def.value=''; def.textContent='Engine default UK voice'; select.appendChild(def);
      const voices=Array.isArray(data?.voices)?data.voices:[];
      voices.forEach(v=>{const opt=document.createElement('option');opt.value=v.name;opt.textContent=voiceLabel(v);select.appendChild(opt);});
      const saved=ttsChoice.engine===selectedEngine ? (ttsChoice.voice||'') : '';
      select.value=[...select.options].some(o=>o.value===saved) ? saved : '';
      select.disabled=false;
      el('voiceLoadStatus').textContent=voices.length ? `${voices.length} English voices available. Use Preview voice to compare them.` : 'This engine did not report any selectable English voices; its UK default can still be used.';
    },
    onTtsVoiceError(message){
      el('ttsVoiceSelect').disabled=false;
      el('voiceLoadStatus').textContent=message||'Could not read that speech engine.';
      toast(message||'Could not read that speech engine.');
    },
    onTtsChoiceSaved(choice){
      ttsChoice=choice||{engine:'',voice:''};
      refreshVoiceSummary();
      show('voiceSetup',false); show('settings');showSettingsPage(settingsCurrentPage);
      toast('Navigation voice saved. It will be used when navigation next starts.');
    },
    onError(message){
      finishRouteCalculationUi();
      const text=message||'Something went wrong';
      if(!el('searchSuggestionsDropdown').classList.contains('hidden')) renderSearchDropdown(null,text);
      toast(text);
    },
    onTransitPreloadAreaResult(ok,message,requestId){if(requestId!==transitPreloadAreaRequestId)return;const b=el('transitPreloadAreaBtn');if(b)b.disabled=false;toast(ok?`Preparing ${message} on your private server…`:(message||'Could not prepare that area.'));},
    onDailyTransitPreloadPermission(granted){if(!granted)toast('Daily area preparation needs background location permission. Destination-triggered preparation will still work.');},
    onApiKeySaved(ok){ if(ok){show('keySetup',false);refreshProviderSettings();toast('TomTom API key saved'); if(trafficVisible)addTrafficLayers();} else toast('Could not save API key'); }
  };

  function openTransitPreferences(){
    document.querySelectorAll('[data-transit-mode]').forEach(cb=>{cb.checked=transitPreferences.modes[cb.dataset.transitMode]!==false;});
    el('transitWalkSpeed').value=transitPreferences.walkSpeed||'normal';el('transitTransferBuffer').value=transitPreferences.transferBuffer||'normal';el('transitAccessibility').value=transitPreferences.accessibility||'none';if(el('transportApiFallbackToggle'))el('transportApiFallbackToggle').checked=!!transitPreferences.transportApiFallback;if(el('dailyTransitPreloadToggle'))el('dailyTransitPreloadToggle').checked=native()?.isDailyTransitPreloadEnabled?.()!==false;show('transitPreferences');native()?.checkOpenRoadServer?.();
  }
  function applyTransitPreferences(){
    const modes={};document.querySelectorAll('[data-transit-mode]').forEach(cb=>modes[cb.dataset.transitMode]=!!cb.checked);
    if(!Object.values(modes).some(Boolean)){toast('Keep at least one transport type enabled.');return;}
    transitPreferences={modes,walkSpeed:el('transitWalkSpeed').value||'normal',transferBuffer:el('transitTransferBuffer').value||'normal',accessibility:el('transitAccessibility').value||'none',transportApiFallback:!!el('transportApiFallbackToggle')?.checked};saveTransitPreferencesLocal();native()?.setDailyTransitPreloadEnabled?.(!!el('dailyTransitPreloadToggle')?.checked);show('transitPreferences',false);if(transitPrefsReturnToSettings){transitPrefsReturnToSettings=false;showSettingsPage('home');show('settings');}if(mode==='transit'&&destination&&routeOrigin()){routeSelectionUserMade=false;selectedRoute=0;selectedRouteId='';calculateRoute();}else{populateRouteOptions();drawRoutes(false);}
  }
  function showSettingsPage(name='home'){
    settingsCurrentPage=name||'home';
    if(settingsCurrentPage==='updates'){const lbl=el('installedVersionLabel');if(lbl)lbl.textContent='OpenRoad '+(native()?.getInstalledAppVersion?.()||'0.6.35');}
    const homeNode=el('settingsHome');if(homeNode)homeNode.classList.toggle('hidden',settingsCurrentPage!=='home');
    document.querySelectorAll('[data-settings-page]').forEach(node=>node.classList.toggle('hidden',node.dataset.settingsPage!==settingsCurrentPage));
    const scroll=el('settingsScroll');if(scroll)scroll.scrollTop=0;
  }
  function openSettingsHome(){showSettingsPage('home');show('settings');}
  function toggleSheetMinimised(sheet){if(!sheet)return;sheet.classList.toggle('minimised');}

  el('searchInput').addEventListener('click',e=>{if(routePlanningActive&&!routePointSelectionActive()){e.preventDefault();if(!routePlannerIsOpen())toggleRoutePlanner();}});

  function openroadPtBackOneScreen(){
    if(routePointSelectionActive()){
      resetRoutePointSelection();hideSearchDropdown();renderRoutePlanner();return;
    }
    if(!el('busStopSheet')?.classList.contains('hidden')){backFromBusStop();return;}
    if(!el('busServiceSheet')?.classList.contains('hidden')){backFromBusService();return;}
    if(!el('transitDetailSheet')?.classList.contains('hidden')){backFromTransitDetail();return;}
    if(!el('transitPreferences')?.classList.contains('hidden')){el('closeTransitPreferencesBtn')?.click();return;}
    if(routePlannerIsOpen()){closeRoutePlanner();return;}
    if(mode==='transit' && transitSearchRequest &&
       transitSearchRequest===routeRequestId){
      cancelActiveRouteRequest();toast('Search cancelled.');return;
    }
    if(mode==='transit'&&routePlanningActive&&!transitNavigation){
      el('clearRouteBtn')?.click();return;
    }
    // During active guidance Back never silently ends navigation.
  }
  function openroadPtXAction(){
    if(mode==='transit' && transitSearchRequest &&
       transitSearchRequest===routeRequestId){
      cancelActiveRouteRequest();
      if(!navigating && !routeResponse)
        showTransitSearchFailure('Search cancelled. No journey was changed.');
      return;
    }
    if(mode==='transit' && transitNavigation){
      if(window.confirm('Stop public transport navigation?'))
        stopTransitNavigation();
      return;
    }
    clearDestination();
  }
  el('ptBackBtn').onclick=e=>{e.stopPropagation();openroadPtBackOneScreen();};
  el('routeSearchClearBtn').onclick=e=>{e.stopPropagation();openroadPtXAction();};
  el('starBtn').onclick=toggleStarMenu;
  el('searchInput').addEventListener('input',()=>{
    if(routePlanningActive&&!routePointSelectionActive())return;
    hideStarMenu();
    if(searchDebounce) clearTimeout(searchDebounce);
    const q=el('searchInput').value.trim();
    const id=++suggestionRequestId; ++mapAreaSearchRequestId;
    clearAreaSearchMarkers();
    if(q.length<2){if(pendingOriginSelection)renderSearchDropdown(null,'');else hideSearchDropdown();return;}
    searchDebounce=setTimeout(()=>requestSearchSuggestions(id),260);
  });
  el('searchInput').addEventListener('focus',()=>{
    hideStarMenu();
    if(routePlanningActive&&!routePointSelectionActive()){if(!routePlannerIsOpen())toggleRoutePlanner();return;}
    const q=el('searchInput').value.trim();
    if(q.length>=2){const id=++suggestionRequestId;requestSearchSuggestions(id);}else if(pendingOriginSelection)renderSearchDropdown(null,'');
  });
  el('searchInput').addEventListener('keydown',e=>{
    if(routePlanningActive&&!routePointSelectionActive()){if(e.key==='Enter'||e.key===' '){e.preventDefault();toggleRoutePlanner();}else if(e.key==='Escape')closeRoutePlanner();return;}
    if(e.key==='Enter'){e.preventDefault();doSearch();}
    else if(e.key==='Escape'){if(routePointSelectionActive())cancelRoutePointSearch();hideSearchDropdown();hideStarMenu();}
  });
  document.addEventListener('pointerdown',e=>{
    if(routePlannerIsOpen() && !e.target?.closest?.('#topUi')) closeRoutePlanner();
  },{passive:true});

  el('settingsSavedBtn').onclick=()=>{show('settings',false);openSavedPlaces(true);};
  el('closeSavedBtn').onclick=()=>{show('savedSheet',false);if(savedReturnToSettings)show('settings');savedReturnToSettings=false;};

  el('driveBtn').onclick=()=>setMode('drive');
  el('cycleBtn').onclick=()=>setMode('cycle');
  el('walkBtn').onclick=()=>setMode('walk');
  el('transitBtn').onclick=()=>setMode('transit');
  el('addTransitStopBtn').onclick=beginAddTransitStop;
  document.querySelectorAll('.transit-ranking button').forEach(btn=>btn.onclick=()=>{const next=btn.dataset.rank||'balanced';if(next===transitPreference)return;transitPreference=next;routeSelectionUserMade=false;selectedRoute=0;selectedRouteId='';saveTransitPreferencesLocal();document.querySelectorAll('.transit-ranking button').forEach(b=>b.classList.toggle('active',b.dataset.rank===transitPreference));if(mode==='transit'&&destination&&routeOrigin())calculateRoute();else{populateRouteOptions();drawRoutes(false);}});
  el('transitSettingsBtn').onclick=()=>{transitPrefsReturnToSettings=false;openTransitPreferences();};
  el('backTransitPreferencesBtn').onclick=()=>el('closeTransitPreferencesBtn').click();
  el('closeTransitPreferencesBtn').onclick=()=>{show('transitPreferences',false);if(transitPrefsReturnToSettings){transitPrefsReturnToSettings=false;showSettingsPage('home');show('settings');}};
  el('applyTransitPreferencesBtn').onclick=applyTransitPreferences;
  el('transitPreloadAreaBtn').onclick=()=>{const q=el('transitPreloadAreaInput').value.trim();if(q.length<2)return toast('Enter a town or postcode.');const id=++transitPreloadAreaRequestId;el('transitPreloadAreaBtn').disabled=true;native()?.preloadTransitArea?.(q,id);};
  function backFromTransitDetail(){if(expandedTrainTimetable){expandedTrainTimetable='';showTransitDetail(selectedRoute);return;}show('transitDetailSheet',false);if(routeResponse&&!transitNavigation)show('routeCard');}
  function backFromBusService(){++busLiveRequestId;++busRouteRequestId;show('busServiceSheet',false);clearBusRouteMarkers();busServiceTargetStop=null;closeRoutePlanner();if(busServiceReturnSheet==='busStopSheet')show('busStopSheet');else if(busServiceReturnSheet==='transitDetailSheet')show('transitDetailSheet');else if(busServiceReturnSheet==='routeCard'&&routeResponse)show('routeCard');if(routeResponse)drawRoutes(false);}
  function backFromBusStop(){++busStopRequestId;show('busStopSheet',false);if(busStopReturnSheet==='busServiceSheet')show('busServiceSheet');else if(busStopReturnSheet==='transitDetailSheet')show('transitDetailSheet');else if(busStopReturnSheet==='routeCard'&&routeResponse)show('routeCard');}
  function closeTransitSheet(sheet){
    ++busStopRequestId;++busRouteRequestId;++busLiveRequestId;
    show(sheet,false);
    if(sheet==='busServiceSheet'){clearBusRouteMarkers();busServiceTargetStop=null;}
    show('transitDetailSheet',false);show('busStopSheet',false);show('busServiceSheet',false);
    if(routeResponse&&!transitNavigation){show('routeCard');drawRoutes(false);}
  }
  el('backTransitDetailBtn').onclick=backFromTransitDetail;
  el('closeTransitDetailBtn').onclick=()=>closeTransitSheet('transitDetailSheet');
  el('backBusServiceBtn').onclick=backFromBusService;
  el('closeBusServiceBtn').onclick=()=>closeTransitSheet('busServiceSheet');
  document.querySelectorAll('[data-bus-tab]').forEach(btn=>btn.onclick=()=>{busServiceTab=btn.dataset.busTab||'timetable';renderBusServiceContent();});
  el('loadBusLiveBtn').onclick=requestBusLive;
  el('backBusStopBtn').onclick=backFromBusStop;
  el('closeBusStopBtn').onclick=()=>closeTransitSheet('busStopSheet');
  ['routeCard','transitDetailSheet','busServiceSheet','busStopSheet'].forEach(id=>{
    const sheet=el(id);if(!sheet)return;const handle=sheet.querySelector('.sheet-handle');let dragStartY=0,dragging=false;
    sheet.addEventListener('click',e=>{
      if(sheet.classList.contains('minimised')){e.preventDefault();e.stopPropagation();sheet.classList.remove('minimised');return;}
      if(e.target?.closest?.('.sheet-handle')&&!dragging){e.preventDefault();e.stopPropagation();sheet.classList.add('minimised');}
    });
    if(handle){
      handle.addEventListener('pointerdown',e=>{dragStartY=e.clientY;dragging=false;handle.setPointerCapture?.(e.pointerId);sheet.classList.add('dragging');});
      handle.addEventListener('pointermove',e=>{if(!dragStartY)return;const dy=e.clientY-dragStartY;if(Math.abs(dy)>8)dragging=true;sheet.style.transform=`translateY(${Math.max(-40,Math.min(120,dy))}px)`;});
      handle.addEventListener('pointerup',e=>{const dy=e.clientY-dragStartY;sheet.style.transform='';sheet.classList.remove('dragging');dragStartY=0;if(dy>36)sheet.classList.add('minimised');else if(dy<-28)sheet.classList.remove('minimised');setTimeout(()=>{dragging=false;},0);});
      handle.addEventListener('pointercancel',()=>{sheet.style.transform='';sheet.classList.remove('dragging');dragStartY=0;dragging=false;});
    }
  });

  el('locateBtn').onclick=()=>{
    if (navigating) return recentreNavigation();
    if(current) renderUserLocation(true);
    else { locating=true; el('locateBtn').classList.add('locating'); toast('Getting your current location…'); }
    native().requestLocation();
  };
  el('viewToggleBtn').onclick=toggleMapView;
  el('navViewToggleBtn').onclick=toggleMapView;

  el('layersBtn').onclick=()=>{updateLayerButtons();show('layersSheet');};
  el('navLayersBtn').onclick=()=>{updateLayerButtons();show('layersSheet');};
  el('closeLayersBtn').onclick=()=>show('layersSheet',false);
  el('trafficLayerBtn').onclick=()=>{
    trafficVisible=!trafficVisible; el('trafficToggle').checked=trafficVisible; native()?.setTrafficVisible?.(trafficVisible);
    if(trafficVisible)addTrafficLayers();else removeTrafficLayers(); updateLayerButtons();
  };
  el('cycleLayerBtn').onclick=()=>{
    cycleLayerVisible=!cycleLayerVisible; ensureCyclewayLayer();
    if(map?.getLayer('clearroute-cycleways')) try{map.setLayoutProperty('clearroute-cycleways','visibility',cycleLayerVisible?'visible':'none');}catch(_){}
    updateLayerButtons();
  };
  el('placesLayerBtn').onclick=openPlacesSheet;
  el('closePlacesBtn').onclick=()=>show('placesSheet',false);
  el('applyPlacesBtn').onclick=applyPlacesSheet;

  function refreshProviderSettings(){
    try{
      const tt=JSON.parse(native()?.getTomTomStatus?.()||'{}');
      el('tomTomMaskedKey').textContent=tt.configured?(tt.masked||'Configured'):'Not configured';
      el('tomTomMaskedKey').classList.toggle('not-configured',!tt.configured);
      tomTomRevealed=false;el('revealTomTomBtn').textContent='👁';el('revealTomTomBtn').title='Reveal';
    }catch(_){}
    try{
      const p=JSON.parse(native()?.getPublicTransportStatus?.()||'{}');
      el('bodsApiKey').value='';
      const gtfsRegions=Array.isArray(p.naptan?.bodsGtfs?.regions)?p.naptan.bodsGtfs.regions:[];
      const gtfsText=gtfsRegions.length?` · schedule cache: ${gtfsRegions.join(', ')}`:' · scheduled routes download on demand';
      el('bodsMaskedKey').textContent='Server-managed';
      el('bodsSummary').textContent=`Scheduled bus routing${gtfsText} · live buses requested via OpenRoad server`; 
      el('bodsSummary').className=`provider-status good`;
      el('tflApiKey').value='';el('tflSecondaryApiKey').value='';
      el('tflMaskedKey').textContent=p.tflConfigured?(p.tflMasked||'Configured'):'Anonymous';
      el('tflSecondaryMaskedKey').textContent=p.tflSecondaryConfigured?(p.tflSecondaryMasked||'Configured'):'Not stored';
      el('tflSummary').textContent=p.tflConfigured?'Primary key active · anonymous fallback remains available':'Anonymous access active · key optional';el('tflSummary').className='provider-status good';
      el('railDataKeyMasked').textContent=p.openRoadServerPaired?'Managed on OpenRoad server':'Pair OpenRoad server first';
      el('darwinSummary').textContent=p.openRoadServerPaired?'Rail Data consumer key is held privately on JustHostMe; check departures to verify service.':'Pair your phone with OpenRoad before checking rail departures.';
      el('darwinSummary').className=`provider-status${p.openRoadServerPaired?' good':''}`;
      el('transportApiId').value='';el('transportApiKey').value='';
      el('transportApiIdMasked').textContent=p.transportApiConfigured?(p.transportApiIdMasked||'Configured'):'Not configured';
      el('transportApiKeyMasked').textContent=p.transportApiConfigured?(p.transportApiMasked||'Configured'):'Not configured';
      el('transportApiSummary').textContent=p.transportApiConfigured?'Credentials stored · optional fallback is off unless enabled in Public transport settings':'Not configured · not required for normal official-data routing';
      el('transportApiSummary').className=`provider-status${p.transportApiConfigured?' good':''}`;
      el('openRoadServerUrl').textContent=p.openRoadServerUrl||'Not configured';
      el('openRoadServerDeviceId').textContent=p.openRoadServerPaired?(p.openRoadServerDeviceId||'Paired'):'Not paired';
      show('openRoadServerPairControls',!p.openRoadServerPaired);
      el('removeOpenRoadServerBtn').disabled=!p.openRoadServerPaired;
      el('checkOpenRoadServerBtn').disabled=!p.openRoadServerPaired;
      el('openRoadServerSummary').textContent=p.openRoadServerPaired?'Secure device-key pairing active · primary timetable router · on-device fallback remains available':'Not paired · OpenRoad will use the slower on-device timetable parser';
      el('openRoadServerSummary').className=`provider-status${p.openRoadServerPaired?' good':''}`;
      const areas=Number(p.naptan?.areas)||0;el('naptanSummary').textContent=areas?`Built in · ${areas} stop area${areas===1?'':'s'} cached`:'Built in · cache fills as routes are used';
    }catch(_){}
  }

  const transitCredentialRevealState={};
  function wireCredentialReveal(buttonId,codeId,credentialName){
    const button=el(buttonId),code=el(codeId);if(!button||!code)return;
    button.onclick=()=>{
      const showing=!!transitCredentialRevealState[credentialName];
      if(showing){transitCredentialRevealState[credentialName]=false;button.textContent='👁';button.title='Reveal';code.classList.remove('revealed');refreshProviderSettings();return;}
      const value=native()?.revealTransitCredential?.(credentialName)||'';
      if(!value)return toast('That credential is not configured.');
      transitCredentialRevealState[credentialName]=true;button.textContent='🙈';button.title='Hide';code.textContent=value;code.classList.add('revealed');
    };
  }
  wireCredentialReveal('revealBodsBtn','bodsMaskedKey','bods');
  wireCredentialReveal('revealTflBtn','tflMaskedKey','tfl');
  wireCredentialReveal('revealTflSecondaryBtn','tflSecondaryMaskedKey','tflSecondary');
  wireCredentialReveal('revealTransportIdBtn','transportApiIdMasked','transportId');
  wireCredentialReveal('revealTransportKeyBtn','transportApiKeyMasked','transportKey');

  el('pairOpenRoadServerBtn').onclick=()=>{
    const code=el('openRoadPairingCode').value.trim();
    if(!code)return toast('Enter the one-time pairing code generated in cPanel.');
    el('pairOpenRoadServerBtn').disabled=true;
    native()?.pairOpenRoadServer?.(code);
  };
  el('checkOpenRoadServerBtn').onclick=()=>{el('checkOpenRoadServerBtn').disabled=true;native()?.checkOpenRoadServer?.();};
  el('removeOpenRoadServerBtn').onclick=()=>{
    if(!confirm('Remove this phone from the private OpenRoad transport server? You will need a new one-time pairing code to reconnect.'))return;
    native()?.removeOpenRoadServerPairing?.();
  };

  el('trafficToggle').onchange=()=>{
    trafficVisible=el('trafficToggle').checked; native()?.setTrafficVisible?.(trafficVisible);
    if(trafficVisible)addTrafficLayers();else removeTrafficLayers(); updateLayerButtons();
  };
  el('searchBias').onchange=()=>native()?.setSearchBiasEnabled?.(el('searchBias').checked);

  el('menuBtn').onclick=()=>{
    refreshHomeUi();
    el('enhancedLocationToggle').checked=!!native()?.isEnhancedLocationEnabled?.();
    el('searchBias').checked=!!native()?.isSearchBiasEnabled?.();
    el('trafficToggle').checked=!!native()?.isTrafficVisible?.();
    el('navAlertMode').value=native()?.getNavigationAlertMode?.() || 'voice';
    ttsEngines=readTtsEngines(); refreshVoiceSummary();
    updateNetworkBanner();contactsEnabled=!!native()?.hasContactsPermission?.();
    el('contactsSearchSummary').textContent=contactsEnabled?'Enabled — contacts with postal addresses appear in search':'Off — enable to show addressed contacts in search';
    el('contactsSearchAction').textContent=contactsEnabled?'On':'Enable';
    refreshProviderSettings();
    showSettingsPage('home');show('settings');
  };
  el('closeSettingsBtn').onclick=()=>show('settings',false);
  el('checkUpdatesBtn').onclick=()=>native()?.checkForUpdates?.();
  el('installUpdateBtn').onclick=()=>native()?.installUpdate?.();
  document.querySelectorAll('[data-settings-open]').forEach(btn=>btn.onclick=()=>showSettingsPage(btn.dataset.settingsOpen||'home'));
  document.querySelectorAll('.settings-page-back').forEach(btn=>btn.onclick=()=>showSettingsPage('home'));
  el('settingsPublicTransportBtn').onclick=()=>{transitPrefsReturnToSettings=true;show('settings',false);openTransitPreferences();};
  el('changeKeyBtn').onclick=()=>{show('settings',false);show('keySetup');};
  el('revealTomTomBtn').onclick=()=>{
    if(!tomTomRevealed){const key=native()?.revealTomTomApiKey?.()||'';if(!key)return toast('TomTom is not configured.');el('tomTomMaskedKey').textContent=key;tomTomRevealed=true;el('revealTomTomBtn').textContent='🙈';el('revealTomTomBtn').title='Hide';}
    else{tomTomRevealed=false;el('revealTomTomBtn').textContent='👁';el('revealTomTomBtn').title='Reveal';refreshProviderSettings();}
  };
  el('contactsSearchBtn').onclick=()=>{if(native()?.hasContactsPermission?.()){toast('Contacts search is already enabled.');}else native()?.requestContactsPermission?.();};
  el('saveTransportApiBtn').onclick=()=>{const id=el('transportApiId').value.trim(),key=el('transportApiKey').value.trim();if(!id||!key)return toast('Enter both TransportAPI app_id and app_key to replace them.');native()?.saveTransportApiCredentials?.(id,key);};
  el('saveBodsBtn').onclick=()=>{const key=el('bodsApiKey').value.trim();if(!key)return toast('Paste your BODS API key first.');native()?.saveBodsApiKey?.(key);};
  el('saveTflBtn').onclick=()=>{const key=el('tflApiKey').value.trim();if(!key)return toast('Paste the replacement TfL primary key first.');native()?.saveTflApiKey?.(key);};
  el('saveTflSecondaryBtn').onclick=()=>{const key=el('tflSecondaryApiKey').value.trim();if(!key)return toast('Paste the replacement TfL secondary key first.');native()?.saveTflSecondaryApiKey?.(key);};
  el('checkRailDeparturesBtn').onclick=()=>{
    const crs=(el('railStationCrs').value||'').trim().toUpperCase();
    if(!/^[A-Z]{3}$/.test(crs))return toast('Enter a three-letter station code, such as BRI.');
    const button=el('checkRailDeparturesBtn');button.disabled=true;
    el('railDepartureResults').classList.remove('rail-board-error');
    el('railDepartureResults').textContent='Checking Rail Data…';
    native()?.checkRailDepartures?.(crs);
  };
  el('getBodsBtn').onclick=()=>native()?.openExternalUrl?.('https://data.bus-data.dft.gov.uk/account/signup/');
  el('getTflBtn').onclick=()=>native()?.openExternalUrl?.('https://api-portal.tfl.gov.uk/');
  el('getDarwinBtn').onclick=()=>native()?.openExternalUrl?.('https://raildata.org.uk/');
  el('getTransportApiBtn').onclick=()=>native()?.openExternalUrl?.('https://developer.transportapi.com/');
  el('enhancedLocationToggle').onchange=()=>native().setEnhancedLocationEnabled(el('enhancedLocationToggle').checked);
  el('navAlertMode').onchange=()=>{const v=el('navAlertMode').value;native().setNavigationAlertMode(v);updateNavSoundButton();if(v==='flash')setTimeout(()=>flashEdges('near'),120);};
  el('testFlashBtn').onclick=()=>flashEdges('near');
  el('chooseVoiceBtn').onclick=openVoiceSetup;
  el('voiceSettingsBtn').onclick=()=>native().openVoiceSettings();
  el('ttsEngineSelect').onchange=requestVoicesForSelectedEngine;
  el('previewVoiceBtn').onclick=()=>native()?.previewTts?.(el('ttsEngineSelect').value||'',el('ttsVoiceSelect').value||'');
  el('saveVoiceBtn').onclick=()=>native()?.saveTtsChoice?.(el('ttsEngineSelect').value||'',el('ttsVoiceSelect').value||'');
  el('cancelVoiceBtn').onclick=()=>{show('voiceSetup',false);show('settings');showSettingsPage(settingsCurrentPage);};
  el('setHomeBtn').onclick=()=>{show('settings',false);show('homeSetup');setTimeout(()=>el('homeSearchInput').focus(),100);};
  el('clearHomeBtn').onclick=()=>native().clearHome();
  el('cancelHomeSetupBtn').onclick=()=>{show('homeSetup',false);show('settings');showSettingsPage('places');};
  el('homeSearchBtn').onclick=doHomeSearch;
  el('homeSearchInput').addEventListener('keydown',e=>{if(e.key==='Enter')doHomeSearch();});
  el('saveKeyBtn').onclick=()=>{const key=el('apiKeyInput').value.trim();if(key.length<8)return toast('Paste a valid TomTom API key');native().saveApiKey(key);el('apiKeyInput').value='';};

  el('directionsBtn').onclick=requestDirections;
  el('saveDestinationBtn').onclick=saveCurrentDestination;
  el('renameDestinationBtn').onclick=renameCurrentDestination;
  el('saveFavouriteNameBtn').onclick=commitFavouriteName;
  el('cancelFavouriteNameBtn').onclick=closeFavouriteNameEditor;
  el('favouriteNameInput').addEventListener('keydown',e=>{if(e.key==='Enter'){e.preventDefault();commitFavouriteName();}});
  el('cancelDestinationBtn').onclick=clearDestination;
  el('clearRouteBtn').onclick=()=>{cancelActiveRouteRequest();routeResponse=null;clearRouteLayers();closeRoutePlanner();setRoutePlanningActive(false);show('routeCard',false);show('destinationCard',true);};
  el('showStepsBtn').onclick=showRouteSteps;
  el('closeStepsBtn').onclick=()=>show('stepsSheet',false);
  el('routePreferencesBtn').onclick=openRoutePreferences;
  el('closeRoutePreferencesBtn').onclick=saveRoutePreferences;
  el('avoidMotorways').onchange=()=>{if(el('avoidMotorways').checked)el('preferMotorways').checked=false;};
  el('preferMotorways').onchange=()=>{if(el('preferMotorways').checked)el('avoidMotorways').checked=false;};
  el('startNavBtn').onclick=()=>{
    if(!destination)return;
    if(originOverride){
      toast('To start navigation, change the start point back to My location.');
      return;
    }
    if(mode==='transit'){startTransitNavigation();return;}
    if(native()?.startNavigationWithStops)native().startNavigationWithStops(selectedRoute,destination.lat,destination.lon,mode,JSON.stringify(transitViaStops));
    else native().startNavigation(selectedRoute,destination.lat,destination.lon,mode);
  };

  el('navSoundBtn').onclick=cycleNavAlertMode;
  el('navAlongRouteBtn').onclick=openAlongRouteSearch;
  el('navOverviewBtn').onclick=showRouteOverview;
  el('stopNavBtn').onclick=()=>{if(transitNavigation)stopTransitNavigation();else native().stopNavigation();};
  el('navOptionsBtn').onclick=()=>show('navOptions');
  el('closeNavOptionsBtn').onclick=()=>show('navOptions',false);
  el('rerouteNowBtn').onclick=()=>{show('navOptions',false);toast('Finding a fresh route…');native()?.forceReroute?.();};
  el('avoidAheadBtn').onclick=()=>{show('navOptions',false);toast('Avoiding the road ahead…');native()?.avoidRoadAhead?.();};
  el('closeAlongRouteBtn').onclick=()=>show('alongRouteSheet',false);
  document.querySelectorAll('.along-route-category[data-query]').forEach(btn=>btn.addEventListener('click',()=>searchAlongRoute(btn.dataset.query||'')));
  el('shazamBtn').onclick=()=>native()?.openShazam?.();

  document.addEventListener('DOMContentLoaded',()=>{
    loadTransitPreferencesLocal();
    contactsEnabled=!!native()?.hasContactsPermission?.();
    trafficVisible=!!native()?.isTrafficVisible?.();
    el('trafficToggle').checked=trafficVisible;
    el('enhancedLocationToggle').checked=!!native()?.isEnhancedLocationEnabled?.();
    el('searchBias').checked=!!native()?.isSearchBiasEnabled?.();
    el('navAlertMode').value=native()?.getNavigationAlertMode?.() || 'voice';
    // Driving is deliberately the default on every app start. Other modes are
    // loaded only after the user explicitly selects them.
    setMode('drive', false);
    readPlaceCategories(); ttsEngines=readTtsEngines(); refreshVoiceSummary(); refreshHomeUi(); updateViewButtons(); updateLayerButtons(); updateNavSoundButton();
    if(!native()?.hasApiKey()) show('keySetup');
    initMap();
  });
})();
