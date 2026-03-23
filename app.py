import streamlit as st
from langchain_community.utilities import SQLDatabase
from langchain_community.agent_toolkits import create_sql_agent
from langchain_groq import ChatGroq
from tools.email_sender import enviar_relatorio_email
import uuid

# 1. Configuracao da Pagina
st.set_page_config(page_title="Assistente Epro", layout="wide")

# CSS Estilo Gemini: Remove setas, limpa popover e faz hover
st.markdown("""
    <style>
    [data-testid="stPopover"] svg { display: none !important; }
    [data-testid="stPopover"] button { 
        border: none !important; 
        background: transparent !important; 
        box-shadow: none !important; 
        padding: 0 !important; 
        color: #808080 !important; 
    }
    [data-testid="stHorizontalBlock"] [data-testid="stPopover"] { 
        opacity: 0; 
        transition: opacity 0.3s ease; 
    }
    [data-testid="stHorizontalBlock"]:hover [data-testid="stPopover"] { 
        opacity: 1; 
    }
    [data-testid="stSidebarNav"] {display: none;}
    </style>
""", unsafe_allow_html=True)

# --- GERENCIAMENTO DE ESTADO ---
if "chats" not in st.session_state: st.session_state.chats = {} 
if "chat_atual" not in st.session_state: st.session_state.chat_atual = None

def nova_conversa():
    id_chat = str(uuid.uuid4())
    st.session_state.chats[id_chat] = {"titulo": "Nova Conversa", "mensagens": [], "fixado": False}
    st.session_state.chat_atual = id_chat

if st.session_state.chat_atual is None: nova_conversa()

# --- SIDEBAR: HISTORICO ---
with st.sidebar:
    st.markdown("### E-Pro Agent")
    if st.button("+ Nova Conversa", use_container_width=True):
        nova_conversa(); st.rerun()
    st.divider()
    st.caption("Conversas Recentes")
    
    ids_ordenados = sorted(st.session_state.chats.keys(), key=lambda x: (st.session_state.chats[x].get("fixado", False), x), reverse=True)
    
    for id_chat in ids_ordenados:
        info = st.session_state.chats[id_chat]
        if not info["mensagens"]: continue

        col_btn, col_menu = st.columns([0.88, 0.12])
        label = f"{'[FIX] ' if info.get('fixado') else ''}{info['titulo'][:20]}"
        tipo = "primary" if id_chat == st.session_state.chat_atual else "secondary"
        
        if col_btn.button(label, key=f"btn_{id_chat}", use_container_width=True, type=tipo):
            st.session_state.chat_atual = id_chat; st.rerun()
        
        with col_menu.popover("⋮"):
            if st.button("Fixar / Desafixar", key=f"fix_{id_chat}", use_container_width=True):
                st.session_state.chats[id_chat]["fixado"] = not info.get("fixado", False); st.rerun()
            if st.button("Excluir", key=f"del_{id_chat}", use_container_width=True, type="primary"):
                del st.session_state.chats[id_chat]
                if not st.session_state.chats: nova_conversa()
                else: st.session_state.chat_atual = list(st.session_state.chats.keys())[-1]
                st.rerun()

    st.divider()
    if st.button("Limpar Tudo", use_container_width=True, type="secondary"):
        st.session_state.chats = {}; nova_conversa(); st.rerun()

# --- AGENTE E DB ---
# 1. Ajuste do limite de caracteres na conexao (max_string_length=3000)
db = SQLDatabase.from_uri(st.secrets["NEON_DB_URL"].replace("postgres://", "postgresql://", 1), max_string_length=3000)
llm = ChatGroq(api_key=st.secrets["GROQ_API_KEY"], model_name="llama-3.3-70b-versatile", temperature=0)

# 2. Prefixo com a nova regra de descricao adicionada ao final
PREFIXO_SISTEMA = """Voce e um assistente tecnico de suporte focado em SQL.
PRIORIDADE: Responda perguntas de contagem ou status DIRETAMENTE no chat.
REGRA DE EMAIL: SO peça e-mail se o usuario usar palavras como "enviar" ou "relatorio".
REGRA DE BANCO DE DADOS: A tabela principal SEMPRE se chama 'chamados', mesmo que perguntem sobre "tickets". As colunas sao 'ticket', 'situacao_tarefa', 'solicitante', 'data_abertura' e 'descricao'.
REGRA DE DATAS: OBRIGATORIO: Exiba a data EXATAMENTE como esta no banco, apenas convertendo para o padrao brasileiro (DD/MM/YYYY HH:MM:SS). NUNCA altere a hora (nao diminua nem some horas) e NUNCA fale sobre fuso horario.
REGRA DE BUSCA DE NOMES: Para buscas de pessoas, substitua espaços por '%' e use ILIKE.
REGRA DE FORMATACAO: NUNCA junte resultados na mesma linha. Para listar os tickets, voce DEVE deixar uma linha em branco (duplo Enter) entre cada um deles. Siga ESTRITAMENTE o formato:
Ticket [ticket] - [situacao_tarefa] - [solicitante] - Aberto em [DD/MM/YYYY HH:MM:SS]
REGRA DE DESCRICAO: Quando o usuario pedir a "descricao", detalhes ou o texto de um ticket, OBRIGATORIO trazer o texto INTACTO e COMPLETO do banco de dados. NUNCA resuma, NUNCA corte o texto e NUNCA use reticencias (...).
"""

agente_sql = create_sql_agent(llm=llm, db=db, agent_type="tool-calling", verbose=True, prefix=PREFIXO_SISTEMA, extra_tools=[enviar_relatorio_email], max_iterations=6, handle_parsing_errors=True)

# --- AREA DO CHAT ---
st.title("Assistente de Suporte Tecnico")
chat_info = st.session_state.chats[st.session_state.chat_atual]

for msg in chat_info["mensagens"]:
    avatar = "👤" if msg["role"] == "user" else "🤖"
    with st.chat_message(msg["role"], avatar=avatar):
        st.markdown(msg["content"])

# --- PROCESSAMENTO DO CHAT ---
if prompt := st.chat_input("Pergunte algo..."):
    chat_info["mensagens"].append({"role": "user", "content": prompt})
    with st.chat_message("user", avatar="👤"):
        st.markdown(prompt)
        
    with st.chat_message("assistant", avatar="🤖"):
        with st.spinner("Analisando..."):
            
            # --- O CÉREBRO INTELIGENTE COM CONTEXTO (ROTEADOR) ---
            # Pega as últimas 3 mensagens para a IA entender do que vocês estao falando
            historico_contexto = " | ".join([m['content'] for m in chat_info["mensagens"][-4:]])
            
            prompt_classificador = f"""
            Analise a conversa recente: [{historico_contexto}]
            A última mensagem do usuario requer buscar dados, continuacao sobre um ticket/chamado, detalhes ou relatorios? Responda APENAS 'SQL'.
            Se for EXCLUSIVAMENTE uma saudacao ou bate-papo generico (ex: 'oi', 'tudo bem', 'como vai', 'obrigado'), responda APENAS 'CHAT'.
            """
            intencao = llm.invoke(prompt_classificador).content.strip().upper()

            if "CHAT" in intencao:
                # Bate-papo natural
                prompt_chat = f"Voce é o E-Pro Agent. Responda de forma natural e amigavel a interacao: '{prompt}'"
                texto_final = llm.invoke(prompt_chat).content.strip()
            
            else:
                # É sobre dados ou continuacao do assunto! Aciona o Agente SQL
                try:
                    historico = "\n".join([f"{m['role']}: {m['content']}" for m in chat_info["mensagens"][-4:]])
                    input_final = f"HISTORICO:\n{historico}\n\nPERGUNTA: {prompt}\n(Vá direto ao ponto e use SQL rapido)"
                    
                    res = agente_sql.invoke({"input": input_final})
                    texto_final = res["output"]
                    
                    if "enviar_relatorio_email" in str(res) and "Sucesso" in str(res):
                        texto_final = "E-mail enviado, favor verificar sua caixa de emails"
                    elif "Agent stopped due to max iterations" in texto_final:
                        texto_final = "A consulta ficou muito complexa e eu precisei parar. Pode tentar fazer a pergunta de uma forma mais simples?"

                except Exception as e:
                    if "max iterations" in str(e).lower():
                        texto_final = "A consulta demorou demais ou o e-mail foi enviado com sucesso em segundo plano."
                    else:
                        texto_final = "Tive um problema tecnico ao buscar esses dados. Pode tentar reformular a pergunta?"
            
            st.markdown(texto_final)
            chat_info["mensagens"].append({"role": "assistant", "content": texto_final})

    # --- LOGICA DE TITULO REFORCADA ---
    if chat_info["titulo"] == "Nova Conversa" and len(chat_info["mensagens"]) >= 2:
        try:
            p_resumo = f"Extraia o assunto principal desta frase em 2 ou 3 palavras: '{prompt}'. Ex: 'Chamados Paulo Basso'. Responda APENAS as palavras, sem pontos ou aspas."
            resumo = llm.invoke(p_resumo).content.strip().replace('"', '').replace('.', '')
            
            if len(resumo) < 3 or "conversa" in resumo.lower():
                chat_info["titulo"] = prompt[:25].capitalize()
            else:
                chat_info["titulo"] = resumo
        except:
            chat_info["titulo"] = prompt[:20]
        
        st.rerun()