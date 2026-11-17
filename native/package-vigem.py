"""Record local client provenance and include buildable source/runtime notices."""
import argparse,hashlib,json,shutil
from pathlib import Path
parser=argparse.ArgumentParser();parser.add_argument('--zig-root',required=True);args=parser.parse_args()
root=Path(__file__).resolve().parents[1];source=root/'native/vigem-client';dest=root/'vendor/vigem/DS5LightClient-source'
dest.mkdir(exist_ok=True)
for path in source.rglob('*'):
    if path.is_file():
        target=dest/path.relative_to(source);target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,target)
for name in ('build-vigem.ps1','package-vigem.py'):shutil.copyfile(root/'native'/name,dest/name)
zig=Path(args.zig_root);notices=root/'vendor/vigem/DS5LightClient-notices';notices.mkdir(exist_ok=True)
for name,relative in [('Zig-MIT.txt','LICENSE'),('libcxx.txt','lib/libcxx/LICENSE.TXT'),('libcxxabi.txt','lib/libcxxabi/LICENSE.TXT'),('libunwind.txt','lib/libunwind/LICENSE.TXT'),('mingw-COPYING.txt','lib/libc/mingw/COPYING')]:
    shutil.copyfile(zig/relative,notices/name)
for name in ('AUTHORS','DISCLAIMER'):
    path=zig/'lib/libc/mingw'/name
    if path.exists():shutil.copyfile(path,notices/('mingw-'+name+'.txt'))
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
data=dict(upstream='https://github.com/nefarius/ViGEmClient',commit='b66d02d57e32cc8595369c53418b843e958649b4',compiler='Zig 0.13.0 x86_64 Windows',compiler_archive_sha256='d859994725ef9402381e557c60bb57497215682e355204d754ee3df75ee3c158',scope='DS5Light Xbox-only client, not a general DS4 replacement',abi=2,dll_sha256=sha(root/'vendor/vigem/DS5LightViGEmClient.dll'),source_sha256={str(p.relative_to(root)).replace('\\','/'):sha(p) for p in source.rglob('*') if p.is_file()})
(root/'vendor/vigem/DS5LightClient-manifest.json').write_text(json.dumps(data,indent=2),encoding='utf8')
print('Local ViGEm client, source and notices prepared:',data['dll_sha256'])
