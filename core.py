import os, sqlite3, json, re, unicodedata, math, tempfile
from html import escape
from zoneinfo import ZoneInfo
from io import BytesIO
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
from datetime import date, timedelta, datetime
from pathlib import Path
import streamlit as st


FOODS = {
 'ovo':155,'pao integral':250,'pao frances':270,'cafe sem acucar':2,'cafe com acucar':40,
 'peito de peru':105,'banana':89,'maca':52,'leite integral':61,'leite desnatado':35,
 'arroz cozido':130,'arroz':130,'feijao cozido':80,'feijao':80,'frango grelhado':165,
 'frango':165,'carne bovina magra':210,'carne':210,'peixe grelhado':130,'peixe':130,
 'tilapia':128,'atum':116,'batata cozida':87,'batata doce':86,'salada':25,
 'legumes':40,'azeite':884,'iogurte natural':65,'queijo minas':264,'inhame cozido':97,'inhame':97,'cuscuz cozido':112,'cuscuz':112,'sonho de valsa':565,'macaxeira cozida':125,'macaxeira':125,'tapioca':230,
 'aveia':389,'macarrao cozido':158,'brocolis':35,'cenoura':41,'laranja':47,
 'mamao':43,'melancia':30,'abacate':160,'castanha':600,'pizza':266,'pizza recheada':350,'bode cozido':190,'carne de bode cozida':190,'hamburguer':260
}
ALIASES={'ovos':'ovo','pães':'pao integral','pao':'pao integral','pão':'pao integral','arroz branco':'arroz cozido','feijão carioca':'feijao','peito de frango':'frango grelhado','café':'cafe sem acucar','tilápia':'tilapia','batata inglesa':'batata cozida','maçã':'maca'}
MEALS=['Café da manhã','Almoço','Jantar']

def norm(s):
 s=unicodedata.normalize('NFKD',str(s)).encode('ascii','ignore').decode().lower()
 return re.sub(r'\s+',' ',s).strip()

def today():
 return datetime.now(ZoneInfo('America/Recife')).date()

def db_path():
 return Path(os.getenv('APP_DB_PATH', 'emagrecimento.db')).expanduser()

def connect():
 path=db_path()
 path.parent.mkdir(parents=True,exist_ok=True)
 c=sqlite3.connect(path,timeout=30)
 c.execute('PRAGMA journal_mode=WAL')
 c.execute('PRAGMA busy_timeout=30000')
 c.execute('CREATE TABLE IF NOT EXISTS meals (id INTEGER PRIMARY KEY, day TEXT, meal TEXT, food TEXT, grams REAL, kcal REAL, source TEXT, created TEXT)')
 c.execute('CREATE TABLE IF NOT EXISTS habits (day TEXT PRIMARY KEY, water INTEGER DEFAULT 0, sleep INTEGER DEFAULT 0, bike INTEGER DEFAULT 0, bike_minutes INTEGER DEFAULT 0, notes TEXT DEFAULT "")')
 c.execute('CREATE TABLE IF NOT EXISTS measures (day TEXT PRIMARY KEY, weight REAL, waist REAL, hip REAL, notes TEXT DEFAULT "")')
 c.execute('CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)')
 cols=[r[1] for r in c.execute('PRAGMA table_info(habits)')];
 if 'fiber' not in cols:c.execute('ALTER TABLE habits ADD COLUMN fiber INTEGER DEFAULT 0')
 c.execute('INSERT OR IGNORE INTO settings VALUES (?,?)',('start',today().isoformat()))
 c.commit();return c

def get_setting(c,k,default):
 r=c.execute('SELECT value FROM settings WHERE key=?',(k,)).fetchone()
 return r[0] if r else default

def set_setting(c,k,v):
 c.execute('INSERT OR REPLACE INTO settings VALUES (?,?)',(k,str(v)));c.commit()

def config(name, default=''):
 if name in os.environ:return os.environ[name]
 try:return st.secrets.get(name,default)
 except (FileNotFoundError, st.errors.StreamlitSecretNotFoundError):return default

def key():
 return config('OPENAI_API_KEY')

def ai_client():
 from openai import OpenAI
 return OpenAI(api_key=key(),timeout=60,max_retries=1)

def transcribe(audio):
 payload=audio.getvalue()
 if not payload or len(payload)>24*1024*1024:
  raise ValueError('Grave um áudio de até 24 MB.')
 model=config('OPENAI_TRANSCRIPTION_MODEL','gpt-transcribe')
 language={'extra_body':{'languages':['pt']}} if model=='gpt-transcribe' else {'language':'pt'}
 return ai_client().audio.transcriptions.create(model=model,file=('refeicao.wav',payload,'audio/wav'),**language).text

def parse_ai(text, research=False):
 if not text.strip() or len(text)>6000:raise ValueError('Informe um relato com até 6.000 caracteres.')
 instructions='''Você é um estimador nutricional de alimentos brasileiros. Extraia APENAS alimentos efetivamente consumidos e quantidades. Retorne JSON objeto {"items":[{"food":"nome em português","grams":150,"kcal_per_100g":130,"confidence":"alta"}]}. Calorias devem refletir preparo citado, óleo e molhos quando informados. Se porção imprecisa, faça estimativa plausível e use confidence baixa. Café puro ~2 kcal/100ml. Não invente refeições. Nunca trate isto como prescrição clínica.'''
 if research:
  # Optional live web search via the OpenAI Responses API; not the ChatGPT app session.
  prompt=instructions + '\nUse reputable Brazilian food composition sources when possible (TBCA, TACO, official manufacturer nutrition labels). Return only the requested JSON. Distinguish estimates from verified weights.\nMeal: ' + text
  resp=ai_client().responses.create(model=config('OPENAI_RESEARCH_MODEL','gpt-4.1-mini'),tools=[{'type':'web_search'}],input=prompt,store=False)
  raw=resp.output_text.strip()
  match=re.search(r'\{[\s\S]*\}',raw)
  if not match: raise ValueError('A pesquisa não retornou JSON; tente sem pesquisa.')
  obj=json.loads(match.group())
 else:
  r=ai_client().chat.completions.create(model=config('OPENAI_NUTRITION_MODEL','gpt-4o-mini'),temperature=0,response_format={'type':'json_object'},messages=[{'role':'system','content':instructions},{'role':'user','content':text}])
  obj=json.loads(r.choices[0].message.content)
 if not isinstance(obj,dict) or not isinstance(obj.get('items'),list) or any(not isinstance(i,dict) for i in obj['items']):raise ValueError('Resposta inválida da estimativa. Tente novamente.')
 return validate_items([{'food':i.get('food'),'grams':i.get('grams'),'kcal100':i.get('kcal_per_100g'),'confidence':i.get('confidence','estimada')} for i in obj['items']]) if obj['items'] else []

def validate_items(items):
 if not items or len(items)>100:raise ValueError('Inclua entre 1 e 100 alimentos.')
 result=[]
 for item in items:
  food=item.get('food')
  if not isinstance(food,str) or not food.strip() or len(food)>200:raise ValueError('Informe o nome de cada alimento (até 200 caracteres).')
  try:grams=float(item['grams']);kcal=float(item['kcal100'])
  except (TypeError,ValueError,KeyError):raise ValueError('Preencha quantidade e calorias de todos os alimentos.') from None
  if not math.isfinite(grams) or not 0<grams<=10000:raise ValueError('Quantidade deve ser maior que zero e até 10.000 g/ml.')
  if not math.isfinite(kcal) or not 0<=kcal<=1000:raise ValueError('Calorias devem estar entre 0 e 1.000 por 100 g/ml.')
  result.append({'food':food.strip(),'grams':grams,'kcal100':kcal,'confidence':str(item.get('confidence','manual'))})
 return result

def save_meal(c,day,meal,items,description):
 if meal not in MEALS:raise ValueError('Refeição inválida.')
 date.fromisoformat(day)
 items=validate_items(items)
 with c:
  c.executemany('INSERT INTO meals(day,meal,food,grams,kcal,source,created) VALUES (?,?,?,?,?,?,?)',[(day,meal,i['food'],i['grams'],i['grams']*i['kcal100']/100,description,datetime.now(ZoneInfo('America/Recife')).isoformat()) for i in items])

def backup_bytes(c):
 # SQLite backup API includes committed WAL changes, unlike a raw file copy.
 with tempfile.TemporaryDirectory() as directory:
  path=Path(directory)/'backup.db'
  dest=sqlite3.connect(path)
  try:c.backup(dest)
  finally:dest.close()
  return path.read_bytes()

def daily_backup(c):
 # Keep one complete snapshot per day, updated on each successful page render.
 # These snapshots survive app restarts when APP_DB_PATH is on a persistent disk.
 folder=db_path().parent/'backups'
 folder.mkdir(parents=True,exist_ok=True)
 destination=folder/f'meu_plano_{today().isoformat()}.db'
 handle,temporary=tempfile.mkstemp(prefix='.backup-',dir=folder)
 os.close(handle)
 try:
  target=sqlite3.connect(temporary)
  try:c.backup(target)
  finally:target.close()
  os.replace(temporary,destination)
 finally:
  if os.path.exists(temporary):os.unlink(temporary)

def export_csv(frame):
 def safe(value):
  if isinstance(value,str) and value.lstrip().startswith(('=','+','-','@','\t','\r','\n')):return "'"+value
  return value
 return frame.map(safe).to_csv(index=False).encode('utf-8-sig')

def parse_local(text):
 # Split on quantity tokens, preserving decimal commas and standalone eggs.
 out=[]
 normalized=norm(text)
 pattern=r'(?<![\w.-])(\d+(?:[.,]\d+)?)\s*(kg|gramas|grama|gr|g|ml|unidades|unidade|fatias|fatia|ovos|ovo)\b\s*(?:de\s+)?'
 matches=list(re.finditer(pattern,normalized))
 aliases={norm(k):norm(v) for k,v in ALIASES.items()}
 names={**{f:f for f in FOODS},**aliases}
 for index,m in enumerate(matches):
  n=float(m.group(1).replace(',','.'));unit=m.group(2)
  desc=normalized[m.end():matches[index+1].start() if index+1<len(matches) else len(normalized)].strip(' ,;.')
  if unit in ('ovo','ovos'):desc='ovo'
  food=next((names[f] for f in sorted(names,key=len,reverse=True) if re.search(r'\b'+re.escape(f)+r'\b',desc)),None)
  if food:
   g=n*1000 if unit=='kg' else n*(50 if unit in ('ovo','ovos','unidades','unidade') else 30 if unit in ('fatia','fatias') else 1)
   out.append({'food':food,'grams':g,'kcal100':FOODS.get(food,100),'confidence':'estimada'})
 return out

WEIGHING_GUIDE = [
    'PESAGEM OFICIAL: TODO SABADO DE MANHA, ao acordar, apos ir ao banheiro e antes de comer ou beber.',
    'Prefira logo ao acordar, depois de urinar e antes de comer ou beber; nao precisa fazer jejum prolongado.',
    'Use a mesma balanca em piso duro e nivelado, sem sapatos, com roupas leves ou semelhantes.',
    'Fique parado no centro da balanca; anote o peso com uma casa decimal.',
    'Meça a cintura no mesmo horario, em pe, ao final de uma expiracao normal, sem apertar a fita.',
    'Compare a tendencia de 2 a 4 semanas; variacoes diarias de agua, sal e intestino sao normais.',
    'Se quiser pesar-se diariamente, use a media de 7 dias, nao apenas uma medicao isolada.'
]

def make_pdf(start_date, target_kcal, meals_data, habits_data, measures_data):
    buf=BytesIO()
    doc=SimpleDocTemplate(buf,pagesize=(21*cm,29.7*cm),leftMargin=1.5*cm,rightMargin=1.5*cm,topMargin=1.5*cm,bottomMargin=1.5*cm)
    styles=getSampleStyleSheet(); story=[]
    def para(t,style='Normal'): return Paragraph(escape(str(t)),styles[style])
    story += [para('MEU PLANO DE EMAGRECIMENTO - 60 DIAS','Title'),Spacer(1,8),para(f'Inicio: {start_date.strftime("%d/%m/%Y")} | Meta: {target_kcal} kcal/dia | 3 refeicoes'),Spacer(1,10)]
    story += [para('PESAGEM OFICIAL: TODO SABADO DE MANHA','Heading2')]
    for line in WEIGHING_GUIDE: story.append(para('• '+line));story.append(Spacer(1,4))
    story += [Spacer(1,10),para('Plano semanal','Heading2')]
    for line in ['Segunda a quinta e domingo: cafe da manha, almoco e jantar.', 'Sexta-feira: sem carnes terrestres; peixe permitido. Jejum de uma refeicao e opcional, sem necessidade de compensar depois.', 'Sabado: uma refeicao livre, mantendo o registro das quantidades e calorias estimadas.', 'Bicicleta: objetivo de 60 minutos, 5 dias por semana, conforme tolerancia.']:story.append(para('• '+line));story.append(Spacer(1,3))
    story += [Spacer(1,8),para('Cardapio padrao com pesos prontos','Heading2')]
    for title,lines in [
      ('Cafe da manha',['Pao frances 50 g; ovos 100 g (2); peito de peru 20 g; queijo minas 30 g; cafe sem acucar 150 ml.']),
      ('Almoco',['Carne magra grelhada 250 g; arroz cozido 50 g; feijao cozido 50 g; azeite 5 g; 1 Sonho de Valsa 20 g.']),
      ('Jantar - escolha uma opcao',['Pao frances 50 g + carne magra 150 g + queijo minas 20 g (~503 kcal)', 'Inhame cozido 250 g + ovos 100 g (2) + queijo minas 30 g + azeite 5 g (~523 kcal)', 'Cuscuz cozido 250 g + ovos 100 g (2) + queijo minas 30 g (~514 kcal)', 'Cuscuz cozido 180 g + carne magra 150 g (~517 kcal)', 'Macaxeira cozida 150 g + carne magra 150 g + azeite 5 g (~565 kcal)', 'Bode cozido magro 160 g + cuscuz cozido 180 g (~506 kcal, sem oleo extra)'])]:
      story.append(para(title,'Heading3'))
      for line in lines: story.append(para(line))
    story += [Spacer(1,8),para('COMPARACAO CALORICA - MESMO PESO PRONTO','Heading2')]
    comp=Table([['Porcao','Carne bovina magra','Peito de frango','Diferenca'],['100 g','210 kcal','165 kcal','45 kcal'],['150 g','315 kcal','248 kcal','67 kcal'],['200 g','420 kcal','330 kcal','90 kcal'],['250 g','525 kcal','413 kcal','112 kcal']],colWidths=[3*cm,5*cm,5*cm,4*cm]);comp.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#EAF0FF')),('GRID',(0,0),(-1,-1),.4,colors.grey),('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),5)]));story += [comp,para('Valores aproximados para carne bovina magra grelhada (210 kcal/100 g) e peito de frango sem pele grelhado (165 kcal/100 g), sem oleo adicional. Sexta-feira: somente peixe como carne.')]
    story += [para('FIBRA: marque diariamente se tomou o suplemento de fibra conforme orientacao. Beba agua suficiente; o suplemento nao substitui frutas, verduras e legumes.'),Spacer(1,6),para('SABADO - REFEICAO LIVRE: 2 fatias de pizza recheada: 700 a 1.000 kcal (referencia 850 kcal). Registrar como almoco ou jantar; substituir, nao adicionar a outra refeicao.'),Spacer(1,6),para('Pesos apos o cozimento; valores aproximados. Escolha apenas um jantar. Sem frutas e vegetais, ha risco de inadequacao nutricional.'),Spacer(1,10),para('Checklist diario - 60 dias','Heading2')]
    habit_map={str(r['day']):r for _,r in habits_data.iterrows()} if not habits_data.empty else {}
    meal_map={(str(r['day']),str(r['meal'])):float(r['kcal']) for _,r in meals_data.groupby(['day','meal'],as_index=False).kcal.sum().iterrows()} if not meals_data.empty else {}
    rows=[['Dia','DATA','Agua','Sono','Bike','Fibra','Cafe','Almoco','Jantar','Total']]
    for i in range(60):
        d=(start_date+timedelta(days=i)).isoformat(); h=habit_map.get(d,{})
        rows.append([f'{i+1:02d}',f'{d[8:10]}/{d[5:7]}/{d[:4]}', 'X' if h.get('water',0) else '___','X' if h.get('sleep',0) else '___','X' if h.get('bike',0) else '___','X' if h.get('fiber',0) else '___',*[f'{meal_map[(d,m)]:.0f}' if (d,m) in meal_map else '____' for m in ['Café da manhã','Almoço','Jantar']],f'{sum(v for (dd,m),v in meal_map.items() if dd==d):.0f}' if any(dd==d for dd,m in meal_map) else '____'])
    for offset in range(0,60,15):
        tab=Table([rows[0]]+rows[1+offset:1+offset+15],colWidths=[.7*cm,2*cm,1.1*cm,1.1*cm,1.1*cm,1.1*cm,2*cm,2*cm,2*cm,2.5*cm],repeatRows=1,rowHeights=[26]+[34]*min(15,len(rows)-1-offset))
        tab.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#DCEBFA')),('GRID',(0,0),(-1,-1),.35,colors.grey),('FONTSIZE',(0,0),(-1,-1),8),('VALIGN',(0,0),(-1,-1),'MIDDLE'),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#F7FAFC')])]))
        story.append(tab)
        if offset<40:story.append(PageBreak())
    story += [PageBreak(),para('Medicoes semanais','Heading2')]
    m_map={str(r['day']):r.to_dict() for _,r in measures_data.iterrows()} if not measures_data.empty else {}
    weekrows=[['Semana / data','Peso (kg)','Cintura (cm)','Quadril (cm)','Observacoes']]
    for i in range(9):
        scheduled=start_date+timedelta(days=(5-start_date.weekday())%7+i*7)
        if scheduled>=start_date+timedelta(days=60):break
        d=scheduled.isoformat(); m=m_map.get(d,{})
        weekrows.append([f'{i+1} - {d[8:10]}/{d[5:7]}',str(m.get('weight','________')) if m else '________',str(m.get('waist','________')) if m else '________',str(m.get('hip','________')) if m else '________','________________'])
    t=Table(weekrows,colWidths=[3*cm,3*cm,3*cm,3*cm,6*cm]);t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#DCEBFA')),('GRID',(0,0),(-1,-1),.4,colors.grey),('FONTSIZE',(0,0),(-1,-1),9),('ROWHEIGHT',(0,1),(-1,-1),25)]));story.append(t)
    story += [Spacer(1,16),para('Todas as medidas registradas','Heading2')]
    for _,r in measures_data.iterrows():
        story.append(para(f'{r["day"]} | {r["weight"]} kg | Cintura: {r["waist"]} cm | Quadril: {r["hip"]} cm | {r["notes"]}'))
    story += [Spacer(1,16),para('Observacoes do checklist','Heading2')]
    for _,r in habits_data.iterrows():
        if r.get('notes') or r.get('bike_minutes',0):story.append(para(f'{r["day"]} | Bicicleta: {r.get("bike_minutes",0)} min | {r.get("notes","")}'))
    story += [Spacer(1,16),para('Refeicoes registradas','Heading2')]
    if meals_data.empty:story.append(para('Nenhuma refeicao registrada ainda.'))
    else:
        for _,r in meals_data.sort_values(['day','meal']).iterrows():story.append(para(f'{r["day"]} | {r["meal"]} | {r["food"]} | {r["grams"]:g} g/ml | {r["kcal"]:.0f} kcal'))
    story += [Spacer(1,14),para('Valores nutricionais sao estimativas. Meta de 1.700 kcal com exercicio frequente pode exigir revisao profissional.','Italic')]
    doc.build(story);return buf.getvalue()

