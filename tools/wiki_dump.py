"""Download every page of wiki.animeexpeditions.com as wikitext (MediaWiki API).
Needs allpages.json / allpages2.json from list=allpages first; writes pages/*.wiki.
The game data (stages, units, enemies) is in Lua modules: fetch
Module:StageData/data etc. the same way and READ them as text — don't execute them."""
import json, urllib.request, urllib.parse, time, os
titles = [p['title'] for f in ('allpages.json','allpages2.json') for p in json.load(open(f))['query']['allpages']]
os.makedirs('pages', exist_ok=True)
out = {}
for i in range(0, len(titles), 50):
    batch = titles[i:i+50]
    q = urllib.parse.urlencode({'action':'query','prop':'revisions','rvprop':'content','rvslots':'main','format':'json','titles':'|'.join(batch),'redirects':'1'})
    req = urllib.request.Request('https://wiki.animeexpeditions.com/w/api.php?'+q, headers={'User-Agent':'Mozilla/5.0 personal-notes'})
    d = json.load(urllib.request.urlopen(req, timeout=60))
    for p in d['query']['pages'].values():
        if 'revisions' in p:
            out[p['title']] = p['revisions'][0]['slots']['main']['*']
    time.sleep(1)
json.dump(out, open('all.json','w'))
for t, txt in out.items():
    open('pages/'+t.replace('/','__')+'.wiki','w').write(txt)
print(len(out), sum(len(v) for v in out.values()))
