#!/usr/bin/env python3
"""Sig's headless interface; use the original Python and browser engines."""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'engine'))
class Parser(argparse.ArgumentParser):
    def error(self,message):
        print(json.dumps({'ok':False,'error':{'code':'usage','message':message}}));raise SystemExit(2)


def main():
    parser=Parser(prog='sig',description='Sig · 签名工作台：本地抠图、配置与显式浏览器工作区',
      epilog='--json: 成功 {ok:true,...}；失败 {ok:false,error:{code,message}}。退出码 / exit codes: 0 成功，1 操作失败，2 用法错误。\n'
      '仅在窗口中：文件选择/拖放/粘贴、实际按快捷键、查看预览、关闭设置；系统剪贴板授权和复制只能真人完成。\n'
      '产品边界：作者私有签名库不向命令公开。普通浏览器的 IndexedDB 不扫描；CLI 工作区用显式 --profile，偏好可经网页导出导入。',
      formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--json',action='store_true')
    sub=parser.add_subparsers(dest='command',required=True)
    sub.add_parser('status',help='只读版本、源码与形态状态；不启动浏览器或创建配置')
    p=sub.add_parser('extract',help='图片文件 → 透明 PNG，同原 Python 引擎')
    p.add_argument('input',type=Path);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--ink',default='black');p.add_argument('--scale',type=int,default=4);p.add_argument('--bias',type=int,default=0)
    p.add_argument('--deline',action='store_true');p.add_argument('--no-denoise',action='store_true')
    p=sub.add_parser('config',help='导出的便携配置：status/import/export（同网页校验）')
    p.add_argument('words',nargs=argparse.REMAINDER)
    p=sub.add_parser('update',help='check：实际读取版本源；同网页版本比较')
    p.add_argument('words',nargs=argparse.REMAINDER)
    p=sub.add_parser('workspace',help='真实网页 IndexedDB/config：status/add/list/export/rename/remove/clear/config-import/config-export/update')
    p.add_argument('action',choices=['status','add','list','export','rename','remove','clear','config-import','config-export','update'])
    p.add_argument('--profile',type=Path,required=True);p.add_argument('--input',type=Path);p.add_argument('--output',type=Path)
    p.add_argument('--id',type=int);p.add_argument('--name');p.add_argument('--yes',action='store_true')
    # Allow --json anywhere without making it an ignored arbitrary argument.
    words=[w for w in sys.argv[1:] if w!='--json']; args=parser.parse_args(words)
    if args.command=='status':
        result={'ok':True,'product':'sig','form':'web','version':json.loads((ROOT/'web/version.json').read_text())['version'],
                'account':'none','images_uploaded':False,'profile_required':True,
                'source':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'web').glob('sig-*.js')}}
    elif args.command in ('config','update'):
        done=subprocess.run(['node',str(ROOT/'tools/sig_config.cjs'),args.command,*args.words,'--json'],capture_output=True,text=True)
        body=json.loads(done.stdout)
        if done.returncode: raise ValueError(str(body.get('error')))
        result={'ok':True,**body}
    elif args.command=='extract':
        if args.bias: raise ValueError('Python engine exposes adaptive threshold only; use workspace with imported browser bias preferences')
        if args.output.exists(): raise ValueError('Output exists; original preserved')
        from sig_extract import extract
        result={'ok':True,**extract(args.input,args.output,ink=args.ink,scale=args.scale,deline=args.deline,denoise=not args.no_denoise)}
    else:
        from browser_session import run
        request={'action':args.action,'id':args.id,'name':args.name}
        if args.action in ('remove','clear') and not args.yes: raise ValueError('Destructive workspace action requires --yes')
        if args.action in ('remove','rename') and args.id is None: raise ValueError('--id required')
        if args.action in ('add','config-import'):
            if not args.input: raise ValueError('--input required')
            if args.action=='add': request.update(data=base64.b64encode(args.input.read_bytes()).decode(),name=args.input.name)
            else: request['value']=json.loads(args.input.read_text())
        result=run(request,args.profile)
        if result.get('ok') is not True: raise ValueError(result.get('error'))
        if args.action=='export':
            if not args.output: raise ValueError('--output directory required')
            outputs=[]
            if args.output.suffix=='.zip':
                import zipfile
                with zipfile.ZipFile(args.output,'x') as archive:
                    for item in result['items']:archive.writestr(f"signature-{item['id']}.png",base64.b64decode(item.pop('data')))
                outputs.append(str(args.output))
            else:
                args.output.mkdir(parents=True,exist_ok=True)
                for item in result['items']:
                    target=args.output/f"signature-{item['id']}.png"
                    with target.open('xb') as file:file.write(base64.b64decode(item.pop('data')))
                    outputs.append(str(target))
            result['outputs']=outputs
        elif args.action=='config-export' and args.output:
            with args.output.open('x') as file:json.dump({k:result[k] for k in ('schema_version','product','settings')},file)
    print(json.dumps(result,ensure_ascii=False,default=lambda v:v.item() if hasattr(v,'item') else str(v)))


if __name__=='__main__':
    try:main()
    except Exception as exc:
        print(json.dumps({'ok':False,'error':{'code':'operation_failed','message':str(exc)}},ensure_ascii=False));sys.exit(1)
