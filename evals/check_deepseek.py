"""Optional published DSH provider probe; temporary files, no model calls."""
from pathlib import Path
import argparse
import json,os,subprocess,tempfile
ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output',type=Path,required=True)
args=parser.parse_args()
output=args.output.expanduser().resolve()
if output.is_relative_to(ROOT): parser.error('Write evaluation results outside the source package.')
with tempfile.TemporaryDirectory(prefix='dev-memory-dsh-provider-') as tmp:
 base=Path(tmp).resolve();home=base/'home';home.mkdir();project=base/'project';project.mkdir();tool=base/'tool';tool.mkdir()
 env={k:os.environ[k] for k in ('PATH','TMPDIR','SYSTEMROOT') if k in os.environ}
 env.update(HOME=str(home),USERPROFILE=str(home),DSH_HOME=str(home/'custom-dsh'),DSH_AGENTS_HOME=str(home/'.agents'),DEV_MEMORY_HOME=str(home/'.dev-memory'),npm_config_cache=str(base/'cache'),npm_config_userconfig=str(home/'.npmrc'),npm_config_globalconfig=os.devnull)
 result=subprocess.run(['python3',str(ROOT/'install.py'),'deepseek','--project',str(project),'--json'],env=env,text=True,capture_output=True,timeout=30)
 assert result.returncode==0,result.stdout+result.stderr
 installed=json.loads(result.stdout)
 result=subprocess.run(['npm','install','--ignore-scripts','--no-audit','--no-fund','--prefix',str(tool),'@deepseek-ai/dsh-skill-filesystem@0.2.0-rc.2'],env=env,text=True,capture_output=True,timeout=100)
 assert result.returncode==0,result.stderr[-1500:]
 script=tool/'check.mjs'
 script.write_text('''import assert from 'node:assert/strict';
import {FileSystemSkillProvider} from '@deepseek-ai/dsh-skill-filesystem';
const warnings=[];
const controller=new AbortController();
const provider=new FileSystemSkillProvider({get:()=>undefined,logger:{warn:(...args)=>warnings.push(args)}}, {signal:controller.signal,invalidate(){}}, {watch:false});
try {
 const found=await provider.list({cwd:process.argv[2]});
 assert(Array.isArray(found));
 const candidate=found.find(s=>s.name==='dev-memory');
 assert(candidate);
 assert.equal(candidate.source,'user-dsh');
 assert.equal(candidate.invocation.modelInvocable,true);
 const definition=await provider.get(candidate,{cwd:process.argv[2]});
 assert(definition.content.includes('Default activation'));
 assert(definition.content.includes('Capture and correction'));
 assert.equal(definition.metadata.version,'0.5.1');
 assert.equal(warnings.length,0);
 console.log(JSON.stringify({status:'passed',package:'@deepseek-ai/dsh-skill-filesystem',version:'0.2.0-rc.2',native_discovery:'user-dsh',native_yaml_parser:true,model_invocable:true,full_body_loaded:true,watchers_disabled:true,model_calls:0}));
} finally {await provider.dispose();controller.abort();}
''')
 result=subprocess.run(['node',str(script),str(project)],env=env,text=True,capture_output=True,timeout=20)
 assert result.returncode==0,result.stdout+result.stderr
 report=json.loads(result.stdout);report.update(runtime_version='0.5.1',synthetic_only=True,real_user_stores_modified=False,actual_dsh_model_e2e='not_run')
output.parent.mkdir(parents=True,exist_ok=True)
output.write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report))
