<?php
/**
 * OpenRoad Transport Server private configuration.
 * This entire directory belongs OUTSIDE public_html, e.g. /home/CPANELUSER/openroad-private.
 * Edit only the dedicated OpenRoad database settings below.
 */
return [
    'db_host' => 'localhost',
    'db_name' => 'CPANELUSER_openroad',
    'db_user' => 'CPANELUSER_openroad',
    'db_password' => 'CHANGE_ME_TO_THE_DATABASE_PASSWORD',

    // Official DfT/BODS South West GTFS download. The updater follows redirects.
    'gtfs_url' => 'https://data.bus-data.dft.gov.uk/timetable/download/gtfs-file/south_west/',
    'region' => 'south_west',

    // Regional preparation policy. South West is permanent; other regions are prepared only
    // after OpenRoad sees a destination there or the optional daily location check finds you there.
    'prepared_region_ttl_days' => 60,
    'regions' => [
        'south_west' => ['label'=>'South West', 'url'=>'https://data.bus-data.dft.gov.uk/timetable/download/gtfs-file/south_west/', 'permanent'=>true,  'bbox'=>[49.8,-6.0,52.2,-1.4]],
        'west_midlands' => ['label'=>'West Midlands', 'url'=>'https://data.bus-data.dft.gov.uk/timetable/download/gtfs-file/west_midlands/', 'permanent'=>false, 'bbox'=>[51.7,-3.3,53.2,-1.2]],
        'east_midlands' => ['label'=>'East Midlands', 'url'=>'https://data.bus-data.dft.gov.uk/timetable/download/gtfs-file/east_midlands/', 'permanent'=>false, 'bbox'=>[51.8,-1.8,53.7,0.2]],
        'south_east' => ['label'=>'South East', 'url'=>'https://data.bus-data.dft.gov.uk/timetable/download/gtfs-file/south_east/', 'permanent'=>false, 'bbox'=>[50.7,-1.9,52.1,1.8]],
        'east_of_england' => ['label'=>'East of England', 'url'=>'https://data.bus-data.dft.gov.uk/timetable/download/gtfs-file/east_of_england/', 'permanent'=>false, 'bbox'=>[51.4,-0.2,53.0,1.9]],
        'north_west' => ['label'=>'North West', 'url'=>'https://data.bus-data.dft.gov.uk/timetable/download/gtfs-file/north_west/', 'permanent'=>false, 'bbox'=>[52.8,-3.6,55.0,-1.9]],
        'north_east' => ['label'=>'North East', 'url'=>'https://data.bus-data.dft.gov.uk/timetable/download/gtfs-file/north_east/', 'permanent'=>false, 'bbox'=>[54.0,-2.7,55.9,-0.8]],
        'yorkshire' => ['label'=>'Yorkshire', 'url'=>'https://data.bus-data.dft.gov.uk/timetable/download/gtfs-file/yorkshire/', 'permanent'=>false, 'bbox'=>[53.2,-2.5,54.8,-0.1]],
    ],
    'timezone' => 'Europe/London',
    'service_days_ahead' => 45,
    'shape_sample_every' => 1,
    'max_results' => 3,

    // Authentication policy. Pairing codes are generated on the server and expire quickly.
    'pairing_minutes' => 30,
    'signed_clock_skew_seconds' => 180,
    'nonce_retention_seconds' => 900,
    'pair_attempts_per_minute' => 8,
    'unsigned_attempts_per_minute' => 30,
    'device_requests_per_minute' => 120,
];
