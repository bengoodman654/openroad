<?php
http_response_code(404);
header('Cache-Control: no-store');
header('X-Robots-Tag: noindex, nofollow, noarchive');
exit;
