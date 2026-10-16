<?php
if(PHP_SAPI!=='cli'){http_response_code(404);exit;}
require_once dirname(__DIR__).'/lib/bootstrap.php';
function has_index(PDO $db,string $table,string $name): bool {
    $q=$db->prepare('SELECT 1 FROM information_schema.statistics WHERE table_schema=DATABASE() AND table_name=? AND index_name=? LIMIT 1');
    $q->execute([$table,$name]);return $q->fetchColumn()!==false;
}
try{
    $db=openroad_db();openroad_schema($db);
    if(!has_index($db,'or_stop_times','idx_stop_depart_cover')){
        echo "Adding departure covering index…\n";
        $db->exec('ALTER TABLE or_stop_times ADD INDEX idx_stop_depart_cover(dataset_id,stop_id,departure_sec,trip_id,stop_sequence)');
    }
    $legacy=(int)openroad_meta($db,'current_dataset','0');
    if($legacy>0 && openroad_region_dataset($db,'south_west')===0){
        $q=$db->prepare("INSERT INTO or_regions(region_key,dataset_id,label,updated_at,last_used_at,permanent) VALUES('south_west',?,'South West',NOW(),NOW(),1) ON DUPLICATE KEY UPDATE dataset_id=VALUES(dataset_id),label=VALUES(label),permanent=1");
        $q->execute([$legacy]);
    } else {
        $db->exec("UPDATE or_regions SET permanent=1,label='South West' WHERE region_key='south_west'");
    }
    $db->exec('DELETE FROM or_journey_cache');
    echo "OpenRoad Transport Server v0.2.2 database upgrade complete.\n";
    echo "Re-run update_gtfs.php south_west once to rebuild Bristol/South-West with full route shapes.\n";
}catch(Throwable $e){fwrite(STDERR,'Upgrade failed: '.$e->getMessage().PHP_EOL);exit(1);}
