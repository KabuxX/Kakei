"""Explicit manual export. No live server lifecycle is invoked."""
import argparse,json
from datetime import datetime,timezone
from pathlib import Path
from demo.export_snapshot import export_demo
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--db',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--curated-places',type=Path,required=True);a=p.parse_args()
 print(json.dumps(export_demo(a.db,a.output,a.curated_places,datetime.now(timezone.utc).isoformat()),ensure_ascii=False,indent=2))
