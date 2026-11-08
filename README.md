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

## Publicação com dados persistentes

O arquivo `render.yaml` prepara um serviço Python de uma instância, com disco de 1 GB em `/var/data` e banco em `/var/data/emagrecimento.db`. O Render exige serviço pago para disco persistente; confira o valor no painel antes de criar. Não use hospedagem com disco temporário para seu diário. Referências: [discos persistentes](https://render.com/docs/disks) e [Blueprint](https://render.com/docs/blueprint-spec).

1. Coloque o código em um repositório privado no GitHub. Não envie `.env`, `.streamlit/secrets.toml`, arquivos `.db`, backups ou a pasta `.venv`.
2. Conecte esse repositório ao Render e crie um **Blueprint** usando `render.yaml`.
3. Defina `APP_PASSWORD` com uma senha forte de 16 a 256 caracteres no painel. `OPENAI_API_KEY` é opcional: pode ficar vazia para usar o registro manual.
4. Confirme o serviço e disco pagos. Espere a implantação terminar e abra a URL HTTPS fornecida pelo Render.
5. Faça login, registre um item de teste, reinicie o serviço e confira se o registro permanece. Depois exclua o item de teste. Verifique também o microfone no celular e baixe um backup.

As credenciais de hospedagem e o endereço público não fazem parte deste projeto. O arquivo de publicação preparado não significa que o app já esteja no ar. Use HTTPS para o microfone funcionar fora do computador local. Mantenha apenas uma instância, pois este app usa SQLite em disco local.

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

- A cada abertura/atualização autenticada bem-sucedida, o app atualiza um backup do dia na pasta `backups` ao lado do banco. Backups de dias anteriores são preservados. Isso não é um serviço agendado: dias sem uso não geram uma nova cópia.
- Em **Histórico e exportação → Baixar backup completo**, guarde uma cópia no computador, de preferência semanalmente. Ela contém refeições, checklist, medidas e configurações, inclusive fora dos 60 dias. PDF e CSV são exportações para leitura, não substituem o backup completo.
- Backups no mesmo disco não protegem contra exclusão/perda desse disco; mantenha também as cópias baixadas.

Para recuperar sem sobrescrever o banco atual:

```bash
.venv/bin/python scripts/restore.py meu_plano_backup_2026-11-08.db --output dados_recuperados/emagrecimento.db
```

O comando valida a integridade e recusa destino existente. Pare o app, defina `APP_DB_PATH` para o caminho restaurado e reinicie. Em produção, o destino precisa ficar dentro do volume persistente. Não copie apenas o arquivo SQLite de um app em execução: use o botão de backup, que inclui alterações já confirmadas no WAL.

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
