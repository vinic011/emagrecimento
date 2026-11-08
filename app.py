from contextlib import closing
from datetime import date
import sqlite3
import pandas as pd
import plotly.express as px
import streamlit as st
from core import connect, get_setting, set_setting, key, parse_ai, parse_local, transcribe, make_pdf, MEALS, today, save_meal, validate_items, export_csv, backup_bytes, daily_backup
from auth import require_login

st.set_page_config(page_title="Meu Plano | 60 dias", page_icon="🚴", layout="wide")

# Streamlit handles viewport sizing; these rules improve touch targets and avoid
# horizontal tab navigation and iOS text-field zoom on narrow displays.
st.html("""
<style>
@media (max-width: 640px) {
  [data-testid="stMainBlockContainer"] {padding-top: 4rem; padding-left: 1rem; padding-right: 1rem;}
  h1 {font-size: 1.8rem !important;}
  h2, h3 {font-size: 1.3rem !important;}
  input, textarea, [data-baseweb="select"] input {font-size: 16px !important;}
  [data-testid="stButton"] button, [data-testid="stFormSubmitButton"] button,
  [data-testid="stDownloadButton"] button {min-height: 44px;}
  [role="tablist"] {display: flex; flex-wrap: wrap; gap: .25rem; overflow: visible;}
  [role="tab"] {flex: 1 1 45%; min-width: 0; min-height: 48px; height: auto; white-space: normal;}
  [role="tab"] p {white-space: normal; text-align: center;}
  [data-baseweb="tab-highlight"], [data-baseweb="tab-border"] {display: none;}
  [role="tab"][aria-selected="true"] {border-bottom: 3px solid currentColor;}
  .st-key-daily_summary [data-testid="stHorizontalBlock"] {flex-direction: row; gap: .5rem;}
  .st-key-daily_summary [data-testid="stColumn"] {min-width: 0; flex: 1 1 0;}
  .st-key-daily_summary [data-testid="stMetricValue"] {font-size: 1.2rem;}
}
</style>
""")

def main():
 require_login()
 with closing(connect()) as c:
  st.title('🚴 Meu Plano de Emagrecimento')
  st.caption('60 dias • 3 refeições por dia • checklist com data • áudio e estimativas com API da OpenAI')
  with st.sidebar:
   st.header('⚙️ Configurações')
   start=st.date_input('Início do plano',date.fromisoformat(get_setting(c,'start',today().isoformat())))
   target=st.number_input('Meta diária (kcal)',min_value=1200,max_value=4000,value=int(get_setting(c,'target','1700')),step=50)
   st.write('Peso inicial: **98 kg** · Altura: **1,70 m** · Idade: **24 anos**')
   if st.button('Salvar configurações'):
    set_setting(c,'start',start.isoformat());set_setting(c,'target',target);st.success('Salvo!')
   st.info('A meta de 1.700 kcal é agressiva com cinco horas semanais de bicicleta. Procure orientação nutricional e ajuste conforme evolução e sintomas.')
   st.caption('Áudio e análise por IA disponíveis.' if key() else 'Registro manual e catálogo local disponíveis. A IA ainda não está configurada.')
  
  day=st.date_input('📅 Data do registro',today(),key='record_day')
  idx=(day-start).days+1
  st.caption(f'Dia {idx} do plano' if 1<=idx<=60 else 'Fora da janela de 60 dias (registros continuam disponíveis)')
  daystr=day.isoformat()
  meals_df=pd.read_sql_query('SELECT * FROM meals WHERE day=?',c,params=(daystr,))
  consumed=float(meals_df.kcal.sum()) if not meals_df.empty else 0
  with st.container(key='daily_summary'):
   col1,col2,col3=st.columns(3)
   col1.metric('Meta diária',f'{target:,} kcal'.replace(',','.'))
   col2.metric('Consumidas',f'{consumed:.0f} kcal')
   col3.metric('Saldo alimentar',f'{target-consumed:+.0f} kcal')
  st.progress(min(consumed/target,1.0))
  st.caption('Saldo = meta menos calorias registradas; não representa seu déficit energético real.')
  
  
  with st.expander('📋 Consultar cardápio e orientações',expanded=False):
   st.subheader('📋 Rotina alimentar padronizada — pesos exatos')
   st.caption('Pesos de carnes, arroz e feijão após cozinhar. Estimativas: marcas, cortes e preparo alteram as calorias. Sem óleo extra além do especificado.')
   plan = {
    'Café da manhã': [('Pão francês',50,135),('Ovos (2 unidades)',100,155),('Peito de peru (1 fatia)',20,21),('Queijo minas (1 fatia)',30,79),('Café sem açúcar',150,3)],
    'Almoço': [('Carne bovina magra grelhada',250,525),('Arroz cozido',50,65),('Feijão cozido',50,40),('Azeite para preparo',5,44),('Sonho de Valsa (1 bombom)',20,113)],
    'Jantar': [('Pão francês',50,135),('Carne bovina magra desfiada',150,315),('Queijo minas',20,53)]
   }
   for meal_name, rows in plan.items():
    with st.expander(f'{meal_name} — {sum(r[2] for r in rows)} kcal estimadas',expanded=False):
     st.dataframe(pd.DataFrame(rows,columns=['Alimento','Quantidade (g/ml)','kcal estimadas']),hide_index=True,width='stretch')
   st.caption(f'Total de referência do cardápio-base: {sum(v[2] for rows in plan.values() for v in rows)} kcal. A meta de {target} kcal é aproximada; ajuste conforme marcas e modo de preparo.')
   st.subheader('🥩 Comparação calórica: carne bovina x frango')
   st.caption('Mesmo peso, alimentos prontos, sem pele, sem empanar e sem óleo adicional. Referências aproximadas: carne bovina magra grelhada 210 kcal/100 g; peito de frango grelhado 165 kcal/100 g.')
   st.dataframe(pd.DataFrame([{'Peso pronto':'100 g','Carne bovina magra':210,'Peito de frango':165,'Diferença':45},{'Peso pronto':'150 g','Carne bovina magra':315,'Peito de frango':248,'Diferença':67},{'Peso pronto':'200 g','Carne bovina magra':420,'Peito de frango':330,'Diferença':90},{'Peso pronto':'250 g','Carne bovina magra':525,'Peito de frango':413,'Diferença':112}],),hide_index=True,width='stretch')
   st.info('Na porção de 250 g do almoço, trocar carne bovina magra por peito de frango reduz aproximadamente 112 kcal. O valor real depende do corte, preparo e óleo. Na sexta-feira, mantenha o peixe em vez de frango ou carne.')
   st.subheader('🍽️ Opções para substituir o jantar (escolha uma)')
   dinner_options = [
    ('Pão com carne e queijo', 'Pão francês 50 g + carne magra pronta 150 g + queijo minas 20 g', 503),
    ('Inhame com ovos', 'Inhame cozido 250 g + 2 ovos 100 g + queijo minas 30 g + azeite 5 g', 523),
    ('Cuscuz com ovos', 'Cuscuz cozido 250 g + 2 ovos 100 g + queijo minas 30 g', 514),
    ('Cuscuz com carne', 'Cuscuz cozido 180 g + carne magra pronta 150 g', 517),
    ('Macaxeira com carne', 'Macaxeira cozida 150 g + carne magra pronta 150 g + azeite 5 g', 565),
    ('Bode cozido com cuscuz', 'Bode cozido magro 160 g + cuscuz cozido 180 g, sem óleo extra', 506),
   ]
   st.dataframe(pd.DataFrame(dinner_options,columns=['Opção','Pesos dos alimentos','kcal estimadas']),hide_index=True,width='stretch')
   st.info('🍕 SÁBADO — REFEIÇÃO LIVRE: 2 fatias de pizza recheada = aproximadamente 700–1.000 kcal; referência prática: 850 kcal. Registre a pizza no almoço OU jantar, no lugar da refeição habitual. Não é uma refeição adicional.')
   st.caption('Inhame, macaxeira, bode e cuscuz pesados depois de cozidos. Não some as opções ao jantar-base: escolha apenas uma. Se acrescentar óleo, manteiga ou molhos, registre também.')
   st.info('Sexta: substitua a carne do almoço por 250 g de peixe grelhado (~325 kcal) e a do jantar por 180 g de peixe (~234 kcal). Não precisa jejuar para emagrecer. Sábado: uma refeição livre registrada, sem compensação extrema.')
   st.warning('Cardápio sem frutas, verduras e legumes não é nutricionalmente completo para 60 dias: pode faltar vitamina C, folato, potássio e fibras. Considere incluir ao menos 1 fruta e alguma fonte vegetal diariamente e buscar nutricionista para adequar a dieta. Peito de peru é ultraprocessado; pode alternar com outra proteína.')
   
  t1,t2,t3,t4=st.tabs(['🍽️ Refeições e áudio','✅ Checklist','📏 Evolução semanal','📊 Histórico e exportação'])
  with t1:
   st.subheader('Registrar uma refeição')
   meal=st.selectbox('Refeição',MEALS,key='meal')
   context=(daystr,meal)
   if st.session_state.get('draft_context')!=context:
    st.session_state.pop('draft',None)
    st.session_state.pop('food_description',None)
    st.session_state['draft_context']=context
    st.session_state['draft_version']=st.session_state.get('draft_version',0)+1
   st.caption('Exemplo: “2 ovos, 60 gramas de pão integral, 40 gramas de peito de peru e 200 ml de café sem açúcar.”')
   st.caption('Ao transcrever ou calcular com IA, o áudio ou relato é enviado à OpenAI. Confira as estimativas antes de salvar.')
   st.caption('No celular, abra o endereço HTTPS no Safari ou Chrome e permita o microfone. Você também pode digitar o relato.')
   audio=st.audio_input('🎙️ Grave o que comeu (opcional)',key=f'audio_{daystr}_{meal}')
   if st.button('Transcrever áudio',disabled=audio is None or not key()):
    try:
     with st.spinner('Transcrevendo áudio…'):
      st.session_state['food_description']=transcribe(audio)
     st.session_state.pop('draft',None)
     st.success('Áudio transcrito. Confira o texto abaixo.')
    except ValueError as e:st.error(str(e))
    except Exception:st.error('Não foi possível transcrever. Confira a configuração e o saldo da API, ou digite o relato.')
   research=st.checkbox('🔎 Consultar fontes na web (usa API e pode ter custo adicional)',value=False,disabled=not key())
   description=st.text_area('Relato da refeição',height=100,key='food_description',max_chars=6000)
   if st.button('Calcular alimentos do relato',type='primary'):
    st.session_state.pop('draft',None)
    st.session_state['draft_version']+=1
    if not description.strip():st.warning('Informe os alimentos e quantidades.')
    else:
     try:
      with st.spinner('Calculando alimentos…'):
       items=parse_ai(description,research=research) if key() else parse_local(description)
      if not items:st.warning('Não reconheci alimentos com quantidades. Use gramas ou adicione manualmente.')
      else:st.session_state['draft']=pd.DataFrame(validate_items(items))
      if not key():st.warning('O catálogo local pode deixar alimentos de fora. Confira cada item e adicione o que faltar; unidades e fatias têm pesos aproximados.')
     except ValueError as e:st.error(str(e))
     except Exception:st.error('Não foi possível estimar pela API. Tente novamente ou adicione os alimentos manualmente.')
   if st.button('Adicionar alimentos manualmente'):
    st.session_state['draft']=pd.DataFrame([{'food':'','grams':100.0,'kcal100':0.0,'confidence':'manual'}])
    st.session_state['draft_version']+=1
   if 'draft' in st.session_state:
    st.markdown('**Confira e edite antes de salvar** — valores são estimativas.')
    version=st.session_state['draft_version']
    edited=[]
    remove=None
    for index,item in enumerate(st.session_state['draft'].to_dict('records')):
     prefix=f'food_{version}_{index}'
     with st.container(border=True):
      st.markdown(f'**Alimento {index+1}**')
      food=st.text_input('Alimento',value=str(item.get('food','')),max_chars=200,key=f'{prefix}_name')
      grams=st.number_input('Quantidade (g/ml)',min_value=.1,max_value=10000.,value=min(10000.,max(.1,float(item.get('grams',100)))),step=1.,key=f'{prefix}_grams')
      kcal=st.number_input('Calorias por 100 g/ml',min_value=0.,max_value=1000.,value=min(1000.,max(0.,float(item.get('kcal100',0)))),step=1.,key=f'{prefix}_kcal')
      edited.append({'food':food,'grams':grams,'kcal100':kcal,'confidence':item.get('confidence','manual')})
      if st.button(f'Remover alimento {index+1}',key=f'{prefix}_remove'):remove=index
    add=st.button('＋ Incluir outro alimento',disabled=len(edited)>=100)
    if remove is not None or add:
     if remove is not None:edited.pop(remove)
     if add:edited.append({'food':'','grams':100.,'kcal100':0.,'confidence':'manual'})
     st.session_state['draft']=pd.DataFrame(edited,columns=['food','grams','kcal100','confidence'])
     st.session_state['draft_version']+=1
     st.rerun()
    draft=pd.DataFrame(edited,columns=['food','grams','kcal100','confidence'])
    try:
     checked=validate_items(draft.to_dict('records'))
     st.write(f"**Total estimado: {sum(i['grams']*i['kcal100']/100 for i in checked):.0f} kcal**")
     valid=True
    except ValueError as e:
     st.warning(str(e));valid=False
    if st.button('💾 Salvar no diário',type='primary',disabled=not valid):
     save_meal(c,daystr,meal,checked,description)
     st.session_state.pop('draft',None)
     st.session_state['saved_meal']=True
     st.rerun()
   if st.session_state.pop('saved_meal',False):st.success('Refeição salva no diário.')
   st.divider()
   st.subheader('Consumo do dia')
   for m in MEALS:
    df=meals_df[meals_df.meal==m] if not meals_df.empty else pd.DataFrame()
    st.markdown(f'**{m} — {df.kcal.sum():.0f} kcal**' if not df.empty else f'**{m} — ainda não registrado**')
    if not df.empty:
     for _,r in df.iterrows():
      a,b=st.columns([6,1]);a.write(f'{r.food} · {r.grams:g} g/ml · {r.kcal:.0f} kcal')
      if b.button('🗑️',key=f'del_{r.id}'):
       c.execute('DELETE FROM meals WHERE id=?',(int(r.id),));c.commit();st.rerun()
   st.info('Sexta-feira: use peixe e alimentos sem carne de boi, frango ou porco. Jejum de uma refeição é opcional; não é necessário reduzir a meta diária. Sábado: uma refeição livre, que também deve ser registrada.')
  with t2:
   st.subheader(f'Checklist de {day.strftime("%d/%m/%Y")}')
   st.caption('Selecione a data no topo da página para preencher dias anteriores ou futuros.')
   existing=c.execute('SELECT water,sleep,bike,bike_minutes,notes,fiber FROM habits WHERE day=?',(daystr,)).fetchone() or (0,0,0,0,'',0)
   with st.form(f'habits_{daystr}'):
    water=st.checkbox('💧 Bebi água suficiente hoje',key=f'water_{daystr}',value=bool(existing[0]))
    sleep=st.checkbox('😴 Dormi bem',key=f'sleep_{daystr}',value=bool(existing[1]))
    fiber=st.checkbox('🌾 Tomei meu suplemento de fibra',key=f'fiber_{daystr}',value=bool(existing[5]))
    bike=st.checkbox('🚴 Pedalei hoje',key=f'bike_{daystr}',value=bool(existing[2]))
    minutes=st.number_input('Minutos de bicicleta',0,300,int(existing[3]),5,key=f'minutes_{daystr}')
    notes=st.text_area('Observações (fome, disposição, dificuldades)',value=existing[4] or '',key=f'notes_{daystr}',max_chars=2000)
    if st.form_submit_button('Salvar checklist',type='primary'):
     c.execute('INSERT OR REPLACE INTO habits (day,water,sleep,bike,bike_minutes,notes,fiber) VALUES (?,?,?,?,?,?,?)',(daystr,int(water),int(sleep),int(bike),int(minutes),notes,int(fiber)));c.commit();st.success('Checklist salvo!')
   st.caption('Suplemento de fibra: use apenas conforme orientação do rótulo ou profissional, com água suficiente. Separe de medicamentos quando indicado. Não substitui uma alimentação variada.')
   st.caption('Objetivo: bicicleta 60 min em 5 dias da semana. Descanso também faz parte do plano.')
   st.write('**Refeições registradas:** '+', '.join(f'{m}: {"✓" if not meals_df.empty and m in meals_df.meal.values else "○"}' for m in MEALS))
  with t3:
   st.subheader('Peso e medidas — uma vez por semana')
   measure=c.execute('SELECT weight,waist,hip,notes FROM measures WHERE day=?',(daystr,)).fetchone()
   with st.form(f'measures_{daystr}'):
    weight=st.number_input('Peso (kg)',key=f'weight_{daystr}',min_value=30.,max_value=250.,value=float(measure[0]) if measure and measure[0] else 98.,step=.1)
    waist=st.number_input('Cintura (cm)',key=f'waist_{daystr}',min_value=40.,max_value=200.,value=float(measure[1]) if measure and measure[1] else 100.,step=.5)
    hip=st.number_input('Quadril (cm)',key=f'hip_{daystr}',min_value=40.,max_value=200.,value=float(measure[2]) if measure and measure[2] else 105.,step=.5)
    note=st.text_input('Observação semanal',value=measure[3] if measure else '',key=f'measure_note_{daystr}',max_chars=2000)
    if st.form_submit_button('Salvar medidas'):
     c.execute('INSERT OR REPLACE INTO measures VALUES (?,?,?,?,?)',(daystr,weight,waist,hip,note));c.commit();st.success('Medidas salvas!')
   st.success('**PESAGEM OFICIAL: TODO SÁBADO DE MANHÃ.** Ao acordar, após ir ao banheiro e antes de comer ou beber. Use a mesma balança e registre peso, cintura e quadril.')
   st.info('**Como se pesar com maior precisão:** pela manhã, após ir ao banheiro, antes do café da manhã e de beber água. Use sempre a mesma balança, no piso firme, sem sapatos e com roupas semelhantes. Não é necessário jejum prolongado. Registre oficialmente todo sábado de manhã; se preferir pesagens diárias, acompanhe a média de 7 dias.')
   st.caption('Meça a cintura sem apertar a fita, após soltar o ar normalmente. Os valores iniciais dos campos são exemplos: substitua pelas medidas reais.')
   measures=pd.read_sql_query('SELECT * FROM measures ORDER BY day',c)
   if not measures.empty:
    st.plotly_chart(px.line(measures,x='day',y='weight',markers=True,title='Evolução do peso (kg)'),width='stretch')
    st.plotly_chart(px.line(measures,x='day',y='waist',markers=True,title='Evolução da cintura (cm)'),width='stretch')
  with t4:
   history=pd.read_sql_query('SELECT day,meal,SUM(kcal) AS kcal FROM meals GROUP BY day,meal ORDER BY day',c)
   if not history.empty:
    daily=history.groupby('day',as_index=False).kcal.sum()
    st.plotly_chart(px.bar(daily,x='day',y='kcal',title='Calorias por dia'),width='stretch')
    st.dataframe(history,width='stretch',hide_index=True)
    st.download_button('⬇️ Exportar refeições CSV',export_csv(pd.read_sql_query('SELECT * FROM meals ORDER BY day',c)),'refeicoes.csv','text/csv')
   habits=pd.read_sql_query('SELECT * FROM habits ORDER BY day',c)
   st.download_button('⬇️ Exportar checklist CSV',export_csv(habits),'checklist.csv','text/csv')
   measures=pd.read_sql_query('SELECT * FROM measures ORDER BY day',c)
   st.download_button('⬇️ Exportar medidas CSV',export_csv(measures),'medidas.csv','text/csv')
   st.divider()
   st.subheader('📄 Gerar PDF para imprimir ou guardar')
   st.caption('Inclui instruções de pesagem, checklist de 60 dias, medidas semanais e refeições já registradas.')
   pdf_bytes=make_pdf(start,target,pd.read_sql_query('SELECT * FROM meals',c),habits,measures)
   st.download_button('📄 Baixar meu PDF atualizado',pdf_bytes,'meu_plano_60_dias.pdf','application/pdf',type='primary')
   st.download_button('💾 Baixar backup completo',backup_bytes(c),f'meu_plano_backup_{today().isoformat()}.db','application/octet-stream')
   st.caption('Guarde uma cópia do backup fora do app. Ele contém todo o diário e as configurações, inclusive registros fora dos 60 dias.')
  try:daily_backup(c)
  except (OSError, sqlite3.Error):
   st.warning('Não foi possível atualizar o backup automático. Baixe o backup completo e confira o espaço de armazenamento.')


if __name__ == "__main__":
 main()
