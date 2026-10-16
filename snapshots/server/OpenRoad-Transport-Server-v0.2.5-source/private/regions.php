<?php
/**
 * Regional BODS preparation catalogue. Kept separate from config.php so upgrades can add
 * coverage without ever overwriting the user's database credentials or security settings.
 */
return [
    'south_west' => ['label'=>'South West', 'url'=>'https://data.bus-data.dft.gov.uk/timetable/download/gtfs-file/south_west/', 'permanent'=>true,  'bbox'=>[49.8,-6.0,52.2,-1.4]],
    'west_midlands' => ['label'=>'West Midlands', 'url'=>'https://data.bus-data.dft.gov.uk/timetable/download/gtfs-file/west_midlands/', 'permanent'=>false, 'bbox'=>[51.7,-3.3,53.2,-1.2]],
    'east_midlands' => ['label'=>'East Midlands', 'url'=>'https://data.bus-data.dft.gov.uk/timetable/download/gtfs-file/east_midlands/', 'permanent'=>false, 'bbox'=>[51.8,-1.8,53.7,0.2]],
    'south_east' => ['label'=>'South East', 'url'=>'https://data.bus-data.dft.gov.uk/timetable/download/gtfs-file/south_east/', 'permanent'=>false, 'bbox'=>[50.7,-1.9,52.1,1.8]],
    'east_of_england' => ['label'=>'East of England', 'url'=>'https://data.bus-data.dft.gov.uk/timetable/download/gtfs-file/east_of_england/', 'permanent'=>false, 'bbox'=>[51.4,-0.2,53.0,1.9]],
    'north_west' => ['label'=>'North West', 'url'=>'https://data.bus-data.dft.gov.uk/timetable/download/gtfs-file/north_west/', 'permanent'=>false, 'bbox'=>[52.8,-3.6,55.0,-1.9]],
    'north_east' => ['label'=>'North East', 'url'=>'https://data.bus-data.dft.gov.uk/timetable/download/gtfs-file/north_east/', 'permanent'=>false, 'bbox'=>[54.0,-2.7,55.9,-0.8]],
    'yorkshire' => ['label'=>'Yorkshire & Humber', 'url'=>'https://data.bus-data.dft.gov.uk/timetable/download/gtfs-file/yorkshire/', 'permanent'=>false, 'bbox'=>[53.2,-2.5,54.8,-0.1]],
];
