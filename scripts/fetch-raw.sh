#!/usr/bin/env bash
# Re-download raw open data into ./raw
set -e
mkdir -p raw
UA="open-webcam-atlas/0.1 (+https://github.com/jaydenbarnescs-tech/open-webcam-atlas)"
curl -s -m 300 -A "$UA" -H "Accept: application/json" https://overpass-api.de/api/interpreter \
  --data-urlencode 'data=[out:json][timeout:280];(nwr["contact:webcam"];nwr["webcam"];);out center tags;' -o raw/osm.json
curl -s -m 60 https://webcams.nyctmc.org/api/cameras -o raw/nyc.json
for d in $(seq 1 12); do dd=$(printf %02d $d); curl -s -m 60 "https://cwwp2.dot.ca.gov/data/d$d/cctv/cctvStatusD$dd.json" -o "raw/ct$dd.json"; done
echo done
