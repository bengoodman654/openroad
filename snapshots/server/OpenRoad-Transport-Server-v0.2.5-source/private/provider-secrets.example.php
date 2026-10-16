<?php
/** COPY to /home/bengoodm/openroad-private/provider-secrets.php (outside public_html).
 *  chmod 600 provider-secrets.php. Never commit or upload credentials to GitHub.
 *  More providers will be migrated incrementally; Rail Data and on-demand BODS live vehicles are active in v0.2.5.
 */
return [
    'raildata_consumer_key' => 'PASTE_YOUR_CONSUMER_KEY_HERE',
    'bods_api_key' => 'PASTE_YOUR_BODS_KEY_HERE',
    // Future: tfl_app_key, tfl_secondary_key, transportapi_app_id, transportapi_app_key
];
