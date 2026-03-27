# E-Pro Agent — Assistente de Suporte Técnico

Chatbot inteligente para consulta e gerenciamento de chamados do sistema 4Biz, com suporte a linguagem natural em português.

---

## Funcionalidades

- Login e cadastro de usuários com senha criptografada
- Recuperação de senha via e-mail com senha temporária e troca obrigatória no primeiro acesso
- Bloqueio de conta após 5 tentativas incorretas de login (30 minutos)
- Histórico de conversas persistente por usuário (salvo no banco de dados), ordenado pelo mais recente
- Paginação do histórico de conversas na sidebar com títulos automáticos por conversa
- Saudação personalizada com o dia da semana e sugestões de perguntas rápidas
- Perfil do usuário com edição de dados e redefinição de senha
- Fixar e excluir conversas na sidebar
- Consultar quantidade de chamados por status (Agendado, Pendente DTI, Em andamento, etc.)
- Listar chamados com filtros por situação ou solicitante
- Visualizar a descrição completa de um chamado
- **Chamados abertos hoje:** retorna lista completa no chat se < 10, ou total + oferta de relatório por e-mail se ≥ 10
- **Resumo Pendentes DTI:** exibe os 10 chamados mais recentes com ticket, solicitante e data de abertura
- **Busca por assunto:** encontra chamados por palavra-chave na descrição, informa a contagem e oferece envio por e-mail
- **Tickets similares:** dado um número de ticket, busca outros chamados com descrição parecida usando extração de frase-chave via LLM
- **Gráfico por status:** pizza interativa com percentual por situação (Plotly)
- **Gráfico por período:** barras dos últimos 6 meses com atualização automática (Plotly)
- Enviar relatórios em CSV por e-mail diretamente pelo chat (sem colunas desnecessárias, datas formatadas em PT-BR)
- Fluxo de e-mail inteligente: confirma o endereço antes de enviar, evita envios duplicados
- Roteador Python inteligente: intercepta gráficos, chamados do dia, busca por assunto e tickets similares antes de chamar o agente SQL
- Roteador de intenção: distingue bate-papo de consultas ao banco

---

## Tecnologias

| Tecnologia | Uso |
|---|---|
| [Streamlit](https://streamlit.io/) | Interface do chatbot |
| [LangChain](https://www.langchain.com/) | Agente SQL e orquestração |
| [Groq + LLaMA 3.3 70B](https://groq.com/) | Modelo de linguagem |
| [PostgreSQL (Neon)](https://neon.tech/) | Banco de dados dos chamados e histórico |
| [bcrypt](https://pypi.org/project/bcrypt/) | Criptografia de senhas |
| [Plotly](https://plotly.com/python/) | Gráficos interativos |
| [smtplib](https://docs.python.org/3/library/smtplib.html) | Envio de e-mail com relatório CSV |

---

## Pré-requisitos

- Python 3.10+
- Conta no [Neon](https://neon.tech/) com as tabelas configuradas
- Conta no [Groq](https://console.groq.com/) para obter a API Key
- Conta Gmail com [Senha de App](https://support.google.com/accounts/answer/185833) habilitada

---

## Banco de Dados

Crie as seguintes tabelas no Neon antes de rodar o projeto:

```sql
-- Tabela de chamados (populada pelo robô extrator)
CREATE TABLE chamados (
    ticket           TEXT PRIMARY KEY,
    situacao_tarefa  TEXT,
    tipo_demanda     TEXT,
    origem           TEXT,
    descricao        TEXT,
    data_abertura    TIMESTAMP,
    data_solucao     TIMESTAMP,
    grupo            TEXT,
    resolvedor       TEXT,
    solicitante      TEXT,
    lotacao          TEXT,
    solucao_resposta TEXT
);

-- Tabela de usuários
CREATE TABLE usuarios (
    id                SERIAL PRIMARY KEY,
    nome              TEXT NOT NULL,
    senha             TEXT NOT NULL,
    email             TEXT UNIQUE NOT NULL,
    senha_temporaria  BOOLEAN DEFAULT FALSE,
    senha_temp_expira TIMESTAMP,
    tentativas_login  INT DEFAULT 0,
    bloqueado_ate     TIMESTAMP,
    criado_em         TIMESTAMP DEFAULT NOW()
);

-- Tabela de histórico de chats
CREATE TABLE historico_chats (
    id            TEXT PRIMARY KEY,
    titulo        TEXT NOT NULL,
    fixado        BOOLEAN DEFAULT FALSE,
    mensagens     JSONB NOT NULL DEFAULT '[]',
    username      TEXT,
    criado_em     TIMESTAMP DEFAULT NOW(),
    atualizado_em TIMESTAMP DEFAULT NOW()
);
```

---

## Instalação

```bash
# Clone o repositório
git clone https://github.com/JeanAres/assistente-suporte-epro.git
cd assistente-suporte-epro

# Crie e ative o ambiente virtual
python -m venv venv
.\venv\Scripts\Activate.ps1  # Windows
source venv/bin/activate     # Linux/Mac

# Instale as dependências
pip install -r requirements.txt
```

---

## Configuração

Crie o arquivo `.streamlit/secrets.toml` na raiz do projeto:

```toml
NEON_DB_URL      = "postgresql://usuario:senha@host/banco"
GROQ_API_KEY     = "sua_groq_api_key"
EMAIL_REMETENTE  = "seu_email@gmail.com"
SENHA_APP_EMAIL  = "sua_senha_de_app"
USUARIO_SISTEMA  = "usuario_4biz"
SENHA_SISTEMA    = "senha_4biz"
```

> **Nunca suba o arquivo `secrets.toml` para o GitHub.** Ele já está no `.gitignore`.

---

## Como rodar

```bash
# Ative o ambiente virtual
.\venv\Scripts\Activate.ps1

# Rode o app
streamlit run app.py
```

Acesse em: `http://localhost:8501`

---

## Sugestões rápidas disponíveis

| Sugestão | Comportamento |
|---|---|
| Quantos chamados foram abertos hoje? | < 10: lista no chat com descrição e solução. ≥ 10: total + oferta de e-mail |
| Resumo dos chamados Pendentes DTI | Top 10 mais recentes com ticket, solicitante e data |
| Gráfico de chamados por status | Pizza interativa por situação |
| Gráfico de chamados por período | Barras dos últimos 6 meses |

---

## Exemplos de uso

```
"Quantos chamados foram abertos hoje?"
"Resumo dos chamados Pendentes DTI"
"Quais são os chamados em andamento?"
"Me mostre os chamados do Paulo Basso"
"Qual a descrição do ticket 1234?"
"Temos algum ticket com descrição parecida com o 166121?"
"Quais chamados falam sobre DOAL?"
"Quero enviar um relatório dos chamados pendentes"
"Gráfico de chamados por status"
```

---

## Estrutura do projeto

```
├── app.py                  # Aplicação principal
├── robo_extrator.py        # Robô que extrai e sincroniza dados do 4Biz
├── tools/
│   ├── __init__.py
│   └── email_sender.py     # Ferramenta de envio de e-mail
├── requirements.txt
├── .gitignore
├── .streamlit/
│   └── secrets.toml        # Variáveis de ambiente (não versionado)
└── README.md
```

---

## Licença

Este projeto é de uso interno. Todos os direitos reservados.