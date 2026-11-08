# Meu Plano — diário pessoal de 60 dias

App Streamlit para uma única pessoa: refeições por texto/áudio, checklist por data, peso e medidas, gráficos, PDF, CSV e backup completo. Os registros continuam disponíveis depois dos 60 dias. A revisão técnica não valida a adequação clínica do cardápio; calorias são estimativas e precisam de conferência.

## Uso local

Python 3.13:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock
.venv/bin/python scripts/configure.py
.venv/bin/streamlit run app.py --server.address=127.0.0.1
```

Abra `http://localhost:8501`. O configurador pede uma senha de 16 a 256 caracteres sem mostrá-la e a grava em `.streamlit/secrets.toml`, excluído do Git. O app bloqueia o diário quando a senha não está configurada. Cinco senhas incorretas provocam bloqueio de um minuto, compartilhado entre sessões do mesmo processo. O acesso expira após 12 horas; use **Sair** em aparelhos compartilhados. Não há cadastro nem separação de dados entre usuários: qualquer pessoa com a senha acessa o mesmo diário.

O banco local existente é preservado. A primeira abertura autenticada fixa a data inicial; você pode alterá-la e clicar em **Salvar configurações**. Datas seguem `America/Recife`.

## Publicar no Streamlit Community Cloud com Neon

**Use `streamlit_app.py` como arquivo principal da publicação.** Esse arquivo exige PostgreSQL externo; se `DATABASE_URL` estiver ausente ou o banco estiver inacessível, o app bloqueia o diário e não muda para SQLite. O Neon armazena refeições, checklist, medidas, configurações e snapshots diários fora da máquina do Streamlit. Reiniciar, hibernar ou reconstruir o app não apaga esse banco externo. Não exclua o projeto/banco no Neon durante o acompanhamento.

### 1. Criar o banco no Neon

1. Crie sua conta no [Neon](https://console.neon.tech) e um projeto dedicado a este diário. Confira as condições e limites do plano oferecido no painel; não é necessário contratar Render.
2. No projeto, abra **Connect**, selecione o banco e copie a **connection string** PostgreSQL. A conexão com **pooling** pode ser usada. Copie somente a URL que começa com `postgresql://`, sem o comando `psql` e sem aspas externas.
3. Guarde a URL com segurança. Ela inclui a senha do banco. Não a envie pelo chat nem coloque no GitHub.

O app cria as tabelas automaticamente no primeiro login; não é necessário executar SQL manualmente. Use um banco dedicado e a credencial com permissão de criar tabelas fornecida pelo Neon. A conexão externa verifica o certificado TLS e o nome do servidor. Referências oficiais: [Streamlit com Neon](https://docs.streamlit.io/develop/tutorials/databases/neon) e [conexão Python](https://neon.com/docs/guides/python).

### 2. Enviar o código ao GitHub

Extraia `dist/meu-plano-community-cloud.zip` e envie o conteúdo para a raiz de um repositório, preferencialmente privado. O pacote já contém o código, `requirements.txt`, `requirements.lock` e `.streamlit/config.toml`. Preserve a pasta `.streamlit`. Não envie `.venv`, `.env`, `.streamlit/secrets.toml`, arquivos `.db` ou backups. O arquivo `secrets.toml.example` tem somente campos vazios e pode ser enviado.

### 3. Criar o app no Community Cloud

Em [Streamlit Community Cloud](https://share.streamlit.io), conecte o repositório e escolha:

| Campo | Valor |
| --- | --- |
| Repository | Seu repositório no GitHub |
| Branch | A branch onde você enviou os arquivos, normalmente `main` |
| Main file path | `streamlit_app.py` |
| Advanced settings → Python version | **3.13** |

Não use o arquivo local `app.py` como entrada no Community Cloud. Selecione Python 3.13 explicitamente nas opções avançadas; o arquivo `.python-version` não substitui essa seleção.

Em **Advanced settings → Secrets**, cole o conteúdo de [.streamlit/secrets.toml.example](.streamlit/secrets.toml.example) e preencha:

```toml
APP_PASSWORD = "sua senha pessoal forte de 16 a 256 caracteres"
DATABASE_URL = "a URL PostgreSQL copiada do Neon"
OPENAI_API_KEY = ""
```

As duas primeiras variáveis são obrigatórias. `OPENAI_API_KEY` pode ficar vazia para usar texto, catálogo local e registro manual. Se quiser áudio e análise por IA, preencha sua chave nesse campo. Não copie as frases de exemplo como credenciais.

Clique em **Deploy**. Para atualizar os Secrets posteriormente, use as configurações do app. Se o repositório for privado, autorize o acesso solicitado pelo Streamlit. O login pessoal por senha continua ativo independentemente da visibilidade escolhida na plataforma. Referências: [publicação](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy) e [Secrets](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/secrets-management).

### 4. Conferir a publicação

Abra a URL `https://SEU-APP.streamlit.app`, faça login, salve um registro de teste e reinicie o app no painel. Entre novamente e confira o registro; depois exclua-o. Verifique também o microfone no celular e baixe um backup completo. Esses passos verificam sua conta e a hospedagem reais, que não são acessadas pelos testes locais.

O código preparado não cria contas, repositórios ou uma URL pública automaticamente. Para instalação anterior com dados locais, use a importação de backup descrita abaixo antes de começar a registrar no Neon.

### Outras hospedagens

`render.yaml` e `compose.yaml` permanecem como alternativas para uso com SQLite e volume persistente. Não são usados pelo Streamlit Community Cloud. No Render, o disco requer serviço pago; a configuração está no arquivo, caso seja útil no futuro.

## Docker e servidor próprio

Copie `.env.example` para `.env` e preencha `APP_PASSWORD`. Então:

```bash
docker compose up -d --build
```

O volume nomeado `diary` guarda banco e backups; os arquivos não ficam dentro da camada descartável do contêiner. A porta está vinculada a `127.0.0.1:8501`; para acesso externo, configure um proxy reverso com HTTPS e suporte a WebSocket. Não execute `docker compose down -v`, pois esse comando apaga o volume. O banco local da pasta do projeto não é enviado automaticamente ao contêiner ou ao Render: para migrar histórico, use o backup.

## Uso no smartphone

Após a publicação, abra a mesma URL HTTPS no navegador do celular e entre com sua senha. O diário fica no servidor, então celular e computador acessam os mesmos registros. O app precisa de conexão com a internet e não funciona offline. `localhost` no celular não é o endereço do app no computador.

O layout para telas estreitas reúne as quatro abas em duas linhas, mantém o cardápio recolhido e usa campos individuais para editar os alimentos. Os botões têm área de toque maior. Abra **Consultar cardápio e orientações** quando quiser consultar as tabelas; tabelas largas permitem rolagem dentro da própria tabela.

Para gravar áudio, abra o link diretamente no Safari ou Chrome, permita o microfone e mantenha a página aberta durante a gravação. HTTPS e permissão são exigidos pelo [acesso ao microfone do navegador](https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/getUserMedia). A transcrição também depende da chave da OpenAI configurada no servidor. Se o navegador interno de outro aplicativo bloquear o microfone, abra o endereço no navegador principal ou digite o relato.

Verificação realizada em Chromium e WebKit com telas móveis e toque simulados (Android: 412 px; iPhone: 390 px). Passaram login, abas sem corte lateral, edição e gravação de refeições, checklist, medidas e downloads de PDF e backup. Esses testes não substituem a confirmação do microfone e do teclado em um aparelho físico após a publicação.

## Backup e recuperação

- No Neon, a cada abertura/atualização autenticada bem-sucedida, o app atualiza o snapshot do dia na tabela `daily_backups` do próprio PostgreSQL. No modo local SQLite, ele grava na pasta `backups` ao lado do banco. Snapshots de dias anteriores são preservados. Isso não é um serviço agendado: dias sem uso não geram uma nova cópia.
- Em **Histórico e exportação → Baixar backup completo**, guarde uma cópia no computador, de preferência semanalmente. Ela contém refeições, checklist, medidas e configurações, inclusive fora dos 60 dias. PDF e CSV são exportações para leitura, não substituem o backup completo.
- Snapshots no mesmo banco ou disco não protegem contra a exclusão desse banco/disco; mantenha também as cópias baixadas fora da hospedagem.

O download continua sendo um arquivo SQLite `.db`, inclusive quando o diário usa PostgreSQL. Ele reúne as quatro tabelas do diário em uma cópia consistente; não inclui senha de acesso nem chave da API.

Para recuperar ou migrar esse backup para um **banco Neon vazio**:

```bash
.venv/bin/python scripts/import_neon.py meu_plano_backup_2026-11-08.db
```

O comando usa `DATABASE_URL` do ambiente/Secrets locais ou pede a URL em entrada oculta. Ele valida o arquivo e recusa sobrescrever um banco que já tenha registros/configurações pessoais. Depois da importação, configure a mesma URL nos Secrets do Community Cloud. Não digite a URL como argumento do comando, para evitar expor a senha no histórico do terminal.

Para recuperar no modo **local SQLite**, sem sobrescrever o banco atual:

```bash
.venv/bin/python scripts/restore.py meu_plano_backup_2026-11-08.db --output dados_recuperados/emagrecimento.db
```

O comando local valida a integridade e recusa destino existente. Pare o app, deixe `DATABASE_URL` vazia, defina `APP_DB_PATH` para o caminho restaurado e reinicie `app.py`. Em produção, o destino precisa ficar dentro do volume persistente. Não copie apenas o arquivo SQLite de um app em execução: use o botão de backup, que inclui alterações já confirmadas no WAL.

## Áudio e estimativas por IA

Configure `OPENAI_API_KEY` no ambiente do servidor ou em `.streamlit/secrets.toml`. Nunca envie a chave pelo chat ou inclua-a no repositório. O uso da API tem cobrança própria. Áudio e texto são enviados à OpenAI somente ao acionar as funções correspondentes. Limites do app: áudio de 24 MB e relato de 6.000 caracteres.

Modelos configuráveis por variáveis de ambiente ou secrets:

| Variável | Padrão |
| --- | --- |
| `OPENAI_TRANSCRIPTION_MODEL` | `gpt-transcribe` |
| `OPENAI_NUTRITION_MODEL` | `gpt-4o-mini` |
| `OPENAI_RESEARCH_MODEL` | `gpt-4.1-mini` |

A transcrição segue a [documentação oficial de áudio](https://developers.openai.com/api/docs/guides/speech-to-text). O modelo antigo `whisper-1` pode ser configurado para compatibilidade, mas sua desativação está prevista para 26/02/2027 conforme essa documentação. A pesquisa usa a ferramenta [web_search da Responses API](https://developers.openai.com/api/docs/guides/tools-web-search) e tem custo adicional. A disponibilidade de modelos depende da conta da API.

Sem chave, use o catálogo local ou **Adicionar alimentos manualmente**. O catálogo pode ignorar alimentos desconhecidos; confira a lista inteira. Unidades/fatias são aproximadas; prefira o peso em gramas. Os campos de cada alimento permitem editar nome, quantidade e calorias antes de salvar, incluir outro alimento ou remover um item. Áudio real, cobrança e acesso aos modelos precisam de validação com uma chave válida na hospedagem.

## Verificações técnicas

```bash
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q
.venv/bin/python -m pip check
```

A suíte usa bancos temporários, sem alterar seu diário. Cobre bloqueio de acesso, limitação de tentativas, troca de datas, refeições, checklist, medidas, exportação PDF, CSV, migração de banco, backup e restauração. Chamadas à API são simuladas nos testes; não comprovam uma chamada real nem o funcionamento físico do microfone.

Para reproduzir os testes de navegador móvel:

```bash
.venv/bin/python -m playwright install chromium webkit
.venv/bin/python scripts/check_mobile.py
```

O teste inicia um servidor local com banco e senha temporários e o encerra ao terminar. Capturas de tela e downloads de teste são gravados em `dist/mobile-qa/`. Os testes de navegador não chamam a API da OpenAI.

Para reproduzir a integração com PostgreSQL real, instale PostgreSQL localmente e execute:

```bash
.venv/bin/python scripts/check_postgres.py
```

O comando cria um cluster temporário isolado, verifica o app pela entrada `streamlit_app.py`, gravação/reconexão, transações, exportação e importação de backup, e encerra o cluster ao terminar. Não usa sua conta do Neon. Os testes PostgreSQL são omitidos na execução comum de `pytest` quando esse cluster temporário não está configurado.
