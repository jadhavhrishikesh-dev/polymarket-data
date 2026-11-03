#!/bin/bash
# Save Polymarket docs pages listed in docs_urls.txt into data/_docs/
mkdir -p data/_docs
while read -r u; do
  [ -z "$u" ] && continue
  f="data/_docs/$(echo "$u" | sed 's#https://##; s#[/?=&]#_#g')"
  curl -sS -m 30 -L "$u" -o "$f" || true
done < docs_urls.txt
