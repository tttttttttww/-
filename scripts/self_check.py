import json, py_compile, re, shutil, subprocess, sys, tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
required=[
 'sources.json','requirements.txt','docs/index.html','docs/data/profile.json','docs/data/items.json',
 'docs/data/source_status.json','docs/data/chains.json','scripts/update.py','scripts/test_logic.py',
 '.github/workflows/update.yml','.github/workflows/deep_update.yml'
]
errors=[]; warnings=[]
for rel in required:
    if not (ROOT/rel).exists(): errors.append('缺少文件: '+rel)
for rel in ['sources.json','docs/data/profile.json','docs/data/items.json','docs/data/source_status.json','docs/data/chains.json']:
    try: json.loads((ROOT/rel).read_text(encoding='utf-8'))
    except Exception as e: errors.append(f'JSON 无效 {rel}: {e}')
for rel in ['scripts/update.py','scripts/test_logic.py']:
    try: py_compile.compile(str(ROOT/rel),doraise=True)
    except Exception as e: errors.append(f'{rel} 语法错误: {e}')
try:
    cfg=json.loads((ROOT/'sources.json').read_text(encoding='utf-8'))
    ids=[x['id'] for x in cfg['sources']]
    if len(ids)!=len(set(ids)): errors.append('sources.json 中存在重复 id')
    seen_urls=[]
    for s in cfg['sources']:
        if not s.get('entry_urls'): errors.append(f"来源 {s.get('id')} 没有入口网址")
        for u in s.get('entry_urls',[]):
            if not u.startswith(('http://','https://')): errors.append(f"来源 {s.get('id')} 的网址格式异常: {u}")
            seen_urls.append((s['id'],u))
    status_obj=json.loads((ROOT/'docs/data/source_status.json').read_text(encoding='utf-8'))
    status=status_obj.get('sources',[])
    status_ids={x.get('source_id') for x in status}
    missing=[x for x in ids if x not in status_ids]
    extra=[x for x in status_ids if x and x not in set(ids)]
    if missing: errors.append('source_status 缺少来源: '+','.join(missing))
    if extra: errors.append('source_status 存在无效来源: '+','.join(extra))
    # Scope guardrails: all 16 Anhui prefecture-level cities + core Jiangsu patrols must remain represented.
    regions={x.get('region','') for x in cfg['sources']}
    anhui=['合肥','芜湖','蚌埠','淮南','马鞍山','淮北','铜陵','安庆','黄山','滁州','阜阳','宿州','六安','亳州','池州','宣城']
    for city in anhui:
        if not any(city in r for r in regions): errors.append('安徽地市覆盖缺失: '+city)
    shanghai_priority={'shanghai-edu','shanghai-rsj-recruit','shanghai-shnu-career','shanghai-baoshan','shanghai-putuo','shanghai-hongkou','shanghai-qingpu'}
    lost_sh=sorted(shanghai_priority-set(ids))
    if lost_sh: errors.append('上海重点来源缺失: '+','.join(lost_sh))
    jiangsu_extra={'jiangsu-suzhou-jyj','jiangsu-wuxi-jyj','jiangsu-nantong-jyj','jiangsu-yangzhou-jyj','jiangsu-zhenjiang-jyj'}
    lost_js=sorted(jiangsu_extra-set(ids))
    if lost_js: errors.append('江苏扩展巡考来源缺失: '+','.join(lost_js))
    priority_ids={'hefei-jyj','hefei-rsj','maanshan-gov','taizhou-jyj','xuzhou-jyj','changzhou-teacher','yancheng-jyj','dafeng-recruit'}
    lost=sorted(priority_ids-set(ids))
    if lost: errors.append('重点来源缺失: '+','.join(lost))
except Exception as e: errors.append('来源配置检查失败: '+str(e))
try:
    p=json.loads((ROOT/'docs/data/profile.json').read_text(encoding='utf-8'))
    for k in ['graduation_year','bachelor_major','master_major','teacher_certificate','target']:
        if not p.get(k): errors.append('profile.json 缺少: '+k)
except Exception as e: errors.append('个人画像检查失败: '+str(e))
# HTML basic integrity + JS syntax if node exists
try:
    html=(ROOT/'docs/index.html').read_text(encoding='utf-8')
    for token in ['data/items.json','data/source_status.json','data/chains.json']:
        if token not in html: errors.append('index.html 未引用 '+token)
    for token in ['官网覆盖','报名截止','我的关注','导出当前列表','导出考试日历','查看官方公告','明确初中语文','有岗位表/附件','历年趋势对比','上海补充','合肥周边','芜湖','合肥全域','我的备注','备考提示']:
        if token not in html: warnings.append('前端可能缺少功能文字: '+token)

    ids=re.findall(r'id=\"([^\"]+)\"',html)
    dup=sorted({x for x in ids if ids.count(x)>1})
    if dup: errors.append('index.html 存在重复 id: '+','.join(dup))
    refs=set(re.findall(r"\$\('([^']+)'\)",html))
    missing=sorted(x for x in refs if x not in set(ids))
    if missing: errors.append('index.html JavaScript 引用了不存在的 id: '+','.join(missing))
    scripts='\n'.join(re.findall(r'<script>(.*?)</script>',html,re.S))
    if shutil.which('node') and scripts:
        with tempfile.NamedTemporaryFile('w',suffix='.js',delete=False,encoding='utf-8') as f:
            f.write(scripts); name=f.name
        r=subprocess.run(['node','--check',name],capture_output=True,text=True)
        Path(name).unlink(missing_ok=True)
        if r.returncode!=0: errors.append('index.html JavaScript 语法错误: '+(r.stderr or r.stdout)[:500])
except Exception as e: errors.append('前端检查失败: '+str(e))
# Workflow guardrails
try:
    quick=(ROOT/'.github/workflows/update.yml').read_text(encoding='utf-8')
    deep=(ROOT/'.github/workflows/deep_update.yml').read_text(encoding='utf-8')
    for nm,txt,mode in [('quick',quick,'--mode quick'),('deep',deep,'--mode deep')]:
        if 'contents: write' not in txt: errors.append(nm+' workflow 缺少 contents: write')
        if 'cancel-in-progress: false' not in txt: errors.append(nm+' workflow 应避免相互取消')
        if mode not in txt: errors.append(nm+' workflow 模式错误')
        if 'scripts/self_check.py' not in txt or 'scripts/test_logic.py' not in txt: errors.append(nm+' workflow 未运行自检/回归测试')
except Exception as e: errors.append('Workflow 检查失败: '+str(e))
if errors:
    print('\n'.join('ERROR: '+x for x in errors)); sys.exit(1)
for x in warnings: print('WARN:',x)
print('SELF CHECK OK')
