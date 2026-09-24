from __future__ import annotations
import json, sys, tempfile, zipfile
from pathlib import Path
PROJECT_ROOT=Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path: sys.path.insert(0,str(PROJECT_ROOT))
from app.core.crimson_desert_archive import CrimsonDesertArchiveAnalyzer

def main():
    a=CrimsonDesertArchiveAnalyzer()
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp); game=root/'Crimson Desert'; (game/'bin64').mkdir(parents=True); (game/'meta').mkdir(); (game/'0000').mkdir(); (game/'bin64'/'CrimsonDesert.exe').write_bytes(b'MZ'); (game/'meta'/'0.papgt').write_bytes(b'x'); (game/'0000'/'0.pamt').write_bytes(b'x')
        ok,msg=a.validate_game_root(game); assert ok,msg
        arc=root/'0009-2426-1-1778403887.zip'; manifest={'format':'crimson_browser_mod_v1','title':'Sample','author':'Tester','version':'1.0'}
        with zipfile.ZipFile(arc,'w',zipfile.ZIP_DEFLATED) as z: z.writestr('0009/manifest.json',json.dumps(manifest)); z.writestr('0009/files/character/test.dds',b'dds')
        r=a.analyze(arc); assert r.format_id=='crimson_browser_mod_v1'; assert r.nexus_mod_id=='2426'; assert r.root_prefix=='0009'; assert r.can_install_with_cdumm
    print('[OK] Crimson Desert archive/game-root smoke test passed.')
    return 0
if __name__=='__main__': raise SystemExit(main())
