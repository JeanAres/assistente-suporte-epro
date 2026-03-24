#  E-Pro Agent — Assistente de Suporte Técnico

Chatbot inteligente para consulta e gerenciamento de chamados do sistema 4Biz, com suporte a linguagem natural em português.


---

##  Funcionalidades

- Consultar quantidade de chamados por status (Agendado, Pendente DTI, Em andamento, etc.)
- Listar chamados com filtros por situação ou solicitante
- Visualizar a descrição completa de um chamado
- Enviar relatórios em CSV por e-mail diretamente pelo chat
- Histórico de conversas com opção de fixar e excluir
- Roteador inteligente: distingue bate-papo de consultas ao banco

---

## 🛠️ Tecnologias

| Tecnologia | Uso |
|---|---|
| [Streamlit](https://streamlit.io/) | Interface do chatbot |
| [LangChain](https://www.langchain.com/) | Agente SQL e orquestração |
| [Groq + LLaMA 3.3 70B](https://groq.com/) | Modelo de linguagem |
| [PostgreSQL (Neon)](https://neon.tech/) | Banco de dados dos chamados |
| [smtplib](https://docs.python.org/3/library/smtplib.html) | Envio de e-mail com relatório CSV |

---

##  Pré-requisitos

- Python 3.10+
- Conta no [Neon](https://neon.tech/) com a tabela `chamados` configurada
- Conta no [Groq](https://console.groq.com/) para obter a API Key
- Conta Gmail com [Senha de App](https://support.google.com/accounts/answer/185833) habilitada

---

##  Instalação

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

##  Configuração

Crie o arquivo `.streamlit/secrets.toml` na raiz do projeto com as seguintes variáveis:

```toml
NEON_DB_URL = "postgresql://usuario:senha@host/banco"
GROQ_API_KEY = "sua_groq_api_key"
EMAIL_REMETENTE = "seu_email@gmail.com"
SENHA_APP_EMAIL = "sua_senha_de_app"
```

>  **Nunca suba o arquivo `secrets.toml` para o GitHub.** Ele já está no `.gitignore`.

---

##  Como rodar

```bash
# Ative o ambiente virtual
.\venv\Scripts\Activate.ps1

# Rode o app
streamlit run app.py
```

Acesse em: `http://localhost:8501`

---

## 💬 Exemplos de uso

```
"Quantos chamados estão agendados?"
"Quais são os chamados em andamento?"
"Me mostre os chamados do Paulo Basso"
"Qual a descrição do ticket 1234?"
"Envie um relatório dos chamados pendentes para meu@email.com"
```

---

##  Estrutura do projeto

```
├── app.py                  # Aplicação principal
├── tools/
│   └── email_sender.py     # Ferramenta de envio de e-mail
├── requirements.txt        # Dependências
├── .gitignore
├── .streamlit/
│   └── secrets.toml        # Variáveis de ambiente (não versionado)
└── README.md
```

---

##  Licença

Este projeto é de uso interno. Todos os direitos reservados.