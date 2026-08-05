import json,re,html,os,urllib.request
from datetime import datetime,timezone,timedelta
from xml.etree import ElementTree as ET
from email.utils import parsedate_to_datetime
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__))); cfg=json.load(open(ROOT+"/config.json",encoding="utf-8"))
def clean(s): return re.sub(r"\s+"," ",re.sub(r"<[^>]+>"," ",html.unescape(s or ""))).strip()
def text(e,names):
 for n in names:
  x=e.find(n)
  if x is not None and x.text:return clean(x.text)
 return ""
def date(s):
 try:return parsedate_to_datetime(s).astimezone(timezone.utc)
 except:
  try:return datetime.fromisoformat(s.replace("Z","+00:00")).astimezone(timezone.utc)
  except:return datetime.now(timezone.utc)
out=[];seen=set()
for f in cfg["feeds"]:
 try:
  req=urllib.request.Request(f["url"],headers={"User-Agent":"PC-GAMING-NOW/1.0"})
  root=ET.fromstring(urllib.request.urlopen(req,timeout=20).read())
  for e in root.findall(".//item")[:20]:
   t=text(e,["title"]);u=text(e,["link"]);d=text(e,["description","{http://purl.org/rss/1.0/modules/content/}encoded"]);p=text(e,["pubDate","published","updated"])
   if t and u:
    k=re.sub(r"\W","",t).lower()
    if k not in seen:seen.add(k);out.append({"title":t,"summary":clean(d)[:120],"url":u,"published":date(p).isoformat(),"source":f["name"],"category":f["category"]})
 except Exception as e:print("feed error",f["name"],e)
cut=datetime.now(timezone.utc)-timedelta(hours=cfg["hours"]);out=[x for x in sorted(out,key=lambda x:x["published"],reverse=True) if date(x["published"])>=cut][:cfg["max_articles"]]
json.dump({"updated_at":datetime.now(timezone.utc).isoformat(),"articles":out},open(ROOT+"/data/news.json","w",encoding="utf-8"),ensure_ascii=False,indent=2)
print("updated",len(out))
