"""Offline regression tests for the most error-prone recruitment parsing rules."""
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import update as u


def check(ok,msg):
    if not ok:
        raise AssertionError(msg)

# 1. Old announcements must not stay in the current/open pool.
check(u.classify('招聘公告','2026-03-05','2026',{}) == '历史考情', 'expired/current-year announcement classification')


check(u.classify('招聘公告','','2027',{})=='近期公告','undated next-cohort announcement visibility')


check(u.guess_date('教师招聘公告','https://x.gov/a.html','报名时间：2026年10月8日。发布日期：2026-10-03')=='2026-10-03','labelled publication date priority')

# 2. Chinese month/day ranges without a repeated year must inherit the cycle year.
s=u.extract_schedule('报名时间：10月8日至10月12日。笔试时间：10月20日。','2026')
check(s.get('apply_start')=='2026-10-08' and s.get('apply_end')=='2026-10-12' and s.get('written_start')=='2026-10-20','schedule fallback-year parsing')


s_short=u.extract_schedule('报名时间：10月8日9:00至12日16:00。','2026')
check(s_short.get('apply_start')=='2026-10-08' and s_short.get('apply_end')=='2026-10-12','same-month shorthand deadline parsing')

# 3. Recruitment-cycle year should prefer “2027届” over publication year.
check(u.detect_cycle_year('某市教育局直属学校2027届校园招聘教师公告','', '2026-10-03')=='2027','2027-cycle detection')


# 3b. For a 2027-campus-recruitment notice published in 2026, omitted month/day dates belong to the publication year, not automatically 2027.
pub='2026-10-03'; cycle='2027'; fallback=(pub[:4] if pub else '') or cycle or u.CURRENT_YEAR
s2=u.extract_schedule('报名时间：10月8日至10月12日。',fallback)
check(s2.get('apply_start')=='2026-10-08' and s2.get('apply_end')=='2026-10-12','publication-year schedule inference for next-cohort recruitment')

# 4. Job matching must stay row-specific and recognize restrictive Chinese-major requirements.
rows=u.extract_target_rows('岗位：初中 语文\n学历：硕士研究生\n专业：汉语言文学\n教师资格：初中及以上语文教师资格证')
check('专业可能受限' in u.match_profile('',rows),'Chinese-major restriction detection')
rows2=u.extract_target_rows('岗位：初中语文\n学历：硕士研究生\n专业：研究生不限专业\n教师资格：初中及以上语文教师资格证')
check('高度关注' in u.match_profile('',rows2),'wide-major detection')


rows3=u.extract_target_rows('岗位：初中语文\n招聘范围：普通高校硕士研究生，本科阶段所学专业须为与招聘岗位相对应的师范类专业\n教师资格：学科学段与招聘岗位一致')
check('专业可能受限' in u.match_profile('',rows3),'bachelor-stage corresponding-major restriction')
cm=u.cert_match(['教师资格证书学科学段与招聘岗位一致'],rows3)
check('教资需核' in cm,'strict stage/subject certificate wording')

# 5. Government attachment links often hide the extension in a query string or anchor text.
check(u.is_attachment_link('https://x.gov.cn/module/download/downfile.jsp?filename=abc.xlsx','岗位表'),'query-string attachment detection')
check(u.attachment_ext('https://x.gov.cn/module/download/downfile.jsp?filename=abc.xlsx','岗位表')=='.xlsx','query-string extension parsing')
check(u.attachment_ext('https://x.gov.cn/download?id=1','附件1：岗位计划表.docx')=='.docx','anchor-text extension parsing')

# 6. Overall ratio/cutoff extraction must remain explicitly numeric and separate from subject ratio.
n=u.extract_numbers('计划公开招聘教师20名。报名人数：400。最低进面分：72.5。')
check(n.get('total_recruit')==20 and n.get('applicants')==400 and n.get('overall_ratio')==20 and n.get('cutoff')==72.5,'number extraction')

# 7. Related stages in one 2027 recruitment should normalize to one chain label.
k=u.chain_key('泰州','2027','关于泰州市教育局直属学校2027届校园招聘教师资格复审公告')
check(k.startswith('泰州|2027|') and '资格复审' not in k and '2027' not in k.split('|')[-1],'chain normalization')


# 8. A hostname containing 'jytyj' must not make every ordinary article link a navigation page.
from bs4 import BeautifulSoup
soup=BeautifulSoup('<a href="/news/123.html">普通新闻</a><a href="/tzgg/index.html">通知公告</a><a href="/teacher/list.html">教师招聘</a>','html.parser')
nav=u.nav_candidates('https://jytyj.example.gov.cn/',soup)
check('https://jytyj.example.gov.cn/news/123.html' not in nav,'hostname false-positive navigation')
check(any('/teacher/list.html' in x for x in nav),'recruitment navigation priority')


# 9. Broad subject words must not turn ordinary teaching-news pages into recruitment records.
check(not u.is_recruitment_candidate('初中语文教学研讨活动顺利举行'),'teaching-news noise filter')
check(not u.is_recruitment_candidate('研究生教育高质量发展论坛召开'),'graduate-news noise filter')
check(u.is_recruitment_candidate('2027届优秀毕业生选聘公告'),'selection announcement discovery')
check(u.is_recruitment_candidate('新任教师资格复审人员名单'),'teacher recruitment stage discovery')


# 10. Deep history crawling must preserve a pagination/navigation frontier instead of re-reading only page 1 forever.
_orig_get=u.get
_pages={
 'https://demo.gov/': '<a href="/recruit/list.html">教师招聘</a>',
 'https://demo.gov/recruit/list.html': '<a href="/recruit/a.html">2025年公开招聘教师公告</a><a href="/recruit/list_2.html">下一页</a>',
 'https://demo.gov/recruit/list_2.html': '<a href="/recruit/b.html">2024年公开招聘教师公告</a>',
 'https://demo.gov/recruit/a.html': '<p>计划公开招聘教师10名。</p>',
 'https://demo.gov/recruit/b.html': '<p>计划公开招聘教师8名。</p>'
}
def _fake_get(url,binary=False):
    if binary:return b''
    if url not in _pages:raise RuntimeError('fixture missing '+url)
    return _pages[url]
u.get=_fake_get
try:
    src={'id':'demo','name':'Demo','region':'Demo','entry_urls':['https://demo.gov/'],'max_pages':1,'quick_pages':1}
    updates1,meta1=u.scan_source(src,{}, {}, 'deep')
    check(meta1.get('pagination_pending',0)>0 and meta1.get('pending_pages'),'deep crawl frontier creation')
    prev={'pending_pages':meta1['pending_pages'],'fingerprint':meta1['fingerprint']}
    updates2,meta2=u.scan_source(src,{},prev,'deep')
    check(any('list.html' in x for x in meta1['pending_pages']) and meta2.get('candidate_count',0)>=1,'deep crawl frontier resume')
finally:
    u.get=_orig_get


# 11. Registration portals should be surfaced separately from the announcement URL.
soup2=BeautifulSoup('<a href="https://exam.example.gov/signup">网上报名入口</a>','html.parser')
regs=u.extract_registration_links('https://edu.example.gov/a.html',soup2,'')
check(regs and 'signup' in regs[0]['url'],'registration-link extraction')

print('LOGIC TESTS OK')

# 12. A 2027 cohort page without publication metadata, discovered in 2026, must not shift month/day-only registration into 2027.
y=u.infer_schedule_year('', '2027', '某市2027届校园招聘教师公告', '')
check(y==str(u.CURRENT_YEAR) if u.CURRENT_YEAR+1==2027 else True, 'undated next-cohort schedule year inference')

# 13. Generic query parameters called source/from may be functional and must not be stripped as tracking parameters.
cu=u.canonical_url('https://x.gov.cn/download?id=7&source=notice&utm_source=test')
check('source=notice' in cu and 'utm_source' not in cu, 'canonical URL functional query preservation')

# 14. When broad graduate wording and an explicit bachelor-major restriction coexist, matching must stay cautious.
rows4=u.extract_target_rows('岗位：初中语文\n学历：硕士研究生，研究生阶段不限专业\n其他：本科阶段所学专业须为与招聘岗位相对应的专业')
check('核实' in u.match_profile('',rows4) and '高度关注' not in u.match_profile('',rows4), 'conflicting major clauses conservative match')

# 15. Generic download endpoints can be typed from response headers/magic bytes.
check(u.infer_attachment_ext('https://x.gov.cn/download?id=1','附件1',{'Content-Type':'application/pdf'},b'%PDF-1.7')=='.pdf','generic PDF sniffing')
check(u.infer_attachment_ext('https://x.gov.cn/download?id=2','附件2',{'Content-Disposition':'attachment; filename="岗位表.xlsx"'},b'PKxx')=='.xlsx','content-disposition extension sniffing')

# 16. Buttons implemented with data-url/onclick should still expose their real link.
soup3=BeautifulSoup('<a data-url="/files/job.xlsx">附件：岗位表</a><a onclick="openWin(\'/signup\')">报名入口</a>','html.parser')
links=[u.element_link('https://edu.example.gov/a.html',a) for a in soup3.find_all('a')]
check(any(x.endswith('/files/job.xlsx') for x in links) and any(x.endswith('/signup') for x in links),'data-url/onclick link extraction')

# 17. Office Open XML attachments behind opaque endpoints can be identified from ZIP member names.
import io, zipfile
bio=io.BytesIO()
with zipfile.ZipFile(bio,'w') as zf:
    zf.writestr('xl/workbook.xml','<x/>')
check(u.infer_attachment_ext('https://x.gov.cn/download?id=9','附件',{'Content-Type':'application/octet-stream'},bio.getvalue())=='.xlsx','OOXML ZIP sniffing')

# 18. Recruitment type should distinguish campus recruitment from social/public recruitment without guessing school-level 'single recruit'.
check(u.detect_recruitment_type('某市教育局直属学校2027届校园招聘教师公告')=='校招','campus recruitment type')
check(u.detect_recruitment_type('某区2026年面向社会公开招聘教师公告')=='社招/公开招聘','social recruitment type')

# 19. Target-subject numbers are extracted only from explicit Chinese-job evidence.
tn=u.extract_target_numbers(['岗位：初中语文 ｜ 招聘人数：2名 ｜ 报名人数：36 ｜ 最低进面分：73.5'])
check(tn.get('target_subject_recruit')==2 and tn.get('target_applicants')==36 and tn.get('target_ratio')==18 and tn.get('target_cutoff')==73.5,'target subject numbers')

# 20. Tabular Chinese-job rows must not absorb the next subject's major restriction.
tabtxt='初中语文 | 硕士研究生 | 研究生不限专业 | 2名\n初中数学 | 硕士研究生 | 数学与应用数学 | 2名'
tr=u.extract_target_rows(tabtxt)
check(tr and '数学与应用数学' not in tr[0] and '研究生不限专业' in tr[0],'tabular row isolation')
