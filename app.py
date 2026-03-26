import streamlit as st
from langchain_community.utilities import SQLDatabase
from langchain_community.agent_toolkits import create_sql_agent
from langchain_groq import ChatGroq
from tools.email_sender import enviar_relatorio_email
import uuid
import psycopg2
import json
import bcrypt
import random
import string
import smtplib
from datetime import datetime, timedelta

# --- CONFIGURACAO DA PAGINA ---
st.set_page_config(page_title="Assistente Epro", layout="wide")

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
    button[kind="secondary"]:has(div p:contains("Esqueci minha senha")) {
        border: none !important;
        background: transparent !important;
        color: #888 !important;
        font-size: 0.8rem !important;
        text-decoration: underline !important;
        padding: 0 !important;
        box-shadow: none !important;
    }

    .saudacao-container {
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        padding: 80px 20px 40px 20px;
        text-align: center;
    }
    .saudacao-texto {
        font-size: 2.4rem;
        font-weight: 600;
        margin-bottom: 8px;
        color: inherit;
    }
    </style>
""", unsafe_allow_html=True)

# --- FUNCOES DE BANCO DE DADOS ---
def get_conn():
    db_url = st.secrets["NEON_DB_URL"]
    if db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgres://", 1)
    return psycopg2.connect(db_url)

# --- FUNCOES DE AUTENTICACAO ---
def cadastrar_usuario(nome, senha, email):
    try:
        conn = get_conn()
        cur = conn.cursor()
        senha_hash = bcrypt.hashpw(senha.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
        cur.execute(
            "INSERT INTO usuarios (nome, senha, email) VALUES (%s, %s, %s)",
            (nome, senha_hash, email)
        )
        conn.commit()
        conn.close()
        return True, "Cadastro realizado com sucesso!"
    except psycopg2.errors.UniqueViolation:
        return False, "Este e-mail já está cadastrado."
    except Exception as e:
        return False, f"Erro ao cadastrar: {e}"

def atualizar_perfil(usuario_id, novo_nome, novo_email):
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute(
            "UPDATE usuarios SET nome = %s, email = %s WHERE id = %s",
            (novo_nome, novo_email, usuario_id)
        )
        conn.commit()
        conn.close()
        return True, "Perfil atualizado com sucesso!"
    except psycopg2.errors.UniqueViolation:
        return False, "Este e-mail já está em uso por outro usuário."
    except Exception as e:
        return False, f"Erro ao atualizar perfil: {e}"

def redefinir_senha(usuario_id, senha_atual, nova_senha):
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT senha FROM usuarios WHERE id = %s", (usuario_id,))
        row = cur.fetchone()
        if not row or not bcrypt.checkpw(senha_atual.encode("utf-8"), row[0].encode("utf-8")):
            conn.close()
            return False, "Senha atual incorreta."
        nova_hash = bcrypt.hashpw(nova_senha.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
        cur.execute("UPDATE usuarios SET senha = %s WHERE id = %s", (nova_hash, usuario_id))
        conn.commit()
        conn.close()
        return True, "Senha alterada com sucesso!"
    except Exception as e:
        return False, f"Erro ao redefinir senha: {e}"

# --- FUNCOES DE CHAT ---
def carregar_chats(email):
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute(
            "SELECT id, titulo, fixado, mensagens FROM historico_chats WHERE username = %s ORDER BY atualizado_em DESC",
            (email,)
        )
        rows = cur.fetchall()
        conn.close()
        chats = {}
        for row in rows:
            chats[row[0]] = {
                "titulo": row[1],
                "fixado": row[2],
                "mensagens": row[3] if isinstance(row[3], list) else json.loads(row[3])
            }
        return chats
    except Exception as e:
        st.error(f"Erro ao carregar chats: {e}")
        return {}

def salvar_chat(id_chat, info, email):
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO historico_chats (id, titulo, fixado, mensagens, username, atualizado_em)
            VALUES (%s, %s, %s, %s::jsonb, %s, NOW())
            ON CONFLICT (id) DO UPDATE SET
                titulo = EXCLUDED.titulo,
                fixado = EXCLUDED.fixado,
                mensagens = EXCLUDED.mensagens,
                atualizado_em = NOW()
        """, (id_chat, info["titulo"], info["fixado"], json.dumps(info["mensagens"]), email))
        conn.commit()
        conn.close()
    except Exception as e:
        st.error(f"Erro ao salvar chat: {e}")

def deletar_chat(id_chat):
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("DELETE FROM historico_chats WHERE id = %s", (id_chat,))
        conn.commit()
        conn.close()
    except Exception as e:
        st.error(f"Erro ao deletar chat: {e}")

def deletar_todos_chats(email):
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("DELETE FROM historico_chats WHERE username = %s", (email,))
        conn.commit()
        conn.close()
    except Exception as e:
        st.error(f"Erro ao limpar chats: {e}")

def get_saudacao():
    dias = {0: "segunda-feira", 1: "terça-feira", 2: "quarta-feira",
            3: "quinta-feira", 4: "sexta-feira", 5: "sábado", 6: "domingo"}
    return f"Feliz {dias[datetime.now().weekday()]}"

def enviar_senha_temporaria(email_destino):
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT id FROM usuarios WHERE email = %s", (email_destino,))
        row = cur.fetchone()
        if not row:
            conn.close()
            return False, "E-mail não encontrado."
        senha_temp = ''.join(random.choices(string.ascii_letters + string.digits, k=10))
        senha_hash = bcrypt.hashpw(senha_temp.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
        expira_em = datetime.now() + timedelta(hours=24)
        cur.execute("UPDATE usuarios SET senha = %s, senha_temporaria = TRUE, senha_temp_expira = %s, tentativas_login = 0, bloqueado_ate = NULL WHERE email = %s", (senha_hash, expira_em, email_destino))
        conn.commit()
        conn.close()
        remetente = st.secrets["EMAIL_REMETENTE"]
        senha_app = st.secrets["SENHA_APP_EMAIL"]
        mensagem = MIMEMultipart()
        mensagem["From"] = remetente
        mensagem["To"] = email_destino
        mensagem["Subject"] = "E-Pro Agent - Senha Temporária"
        corpo = f"Olá,\n\nSua senha temporária é: {senha_temp}\n\nEsta senha é válida por 24 horas. Ao acessar o sistema, você será solicitado a cadastrar uma nova senha.\n\nAtenciosamente,\nE-Pro Agent"
        mensagem.attach(MIMEText(corpo, "plain", "utf-8"))
        servidor = smtplib.SMTP("smtp.gmail.com", 587)
        servidor.starttls()
        servidor.login(remetente, senha_app)
        servidor.send_message(mensagem)
        servidor.quit()
        return True, "Senha temporária enviada para seu e-mail!"
    except Exception as e:
        return False, f"Erro ao enviar e-mail: {e}"

def login_usuario_completo(email, senha):
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT id, nome, senha, senha_temporaria, tentativas_login, bloqueado_ate, senha_temp_expira FROM usuarios WHERE email = %s", (email,))
        row = cur.fetchone()

        if not row:
            conn.close()
            return False, "E-mail ou senha incorretos.", False

        usuario_id, nome, senha_hash, is_temp, tentativas, bloqueado_ate, senha_temp_expira = row

        # Verifica se está bloqueado
        if bloqueado_ate and datetime.now() < bloqueado_ate:
            minutos = int((bloqueado_ate - datetime.now()).total_seconds() / 60) + 1
            conn.close()
            return False, f"Conta bloqueada. Tente novamente em {minutos} minuto(s) ou redefina sua senha.", False

        # Senha correta
        if bcrypt.checkpw(senha.encode("utf-8"), senha_hash.encode("utf-8")):
            # Verifica se senha temporaria expirou
            if is_temp and senha_temp_expira and datetime.now() > senha_temp_expira:
                cur.execute("UPDATE usuarios SET senha_temporaria = FALSE, senha_temp_expira = NULL WHERE id = %s", (usuario_id,))
                conn.commit()
                conn.close()
                return False, "Sua senha temporária expirou. Solicite uma nova pelo link 'Esqueci minha senha'.", False
            cur.execute("UPDATE usuarios SET tentativas_login = 0, bloqueado_ate = NULL WHERE id = %s", (usuario_id,))
            conn.commit()
            conn.close()
            return True, {"id": usuario_id, "nome": nome, "email": email}, is_temp

        # Senha errada — incrementa tentativas
        novas_tentativas = (tentativas or 0) + 1
        if novas_tentativas >= 5:
            bloqueio = datetime.now() + timedelta(minutes=30)
            cur.execute("UPDATE usuarios SET tentativas_login = %s, bloqueado_ate = %s WHERE id = %s", (novas_tentativas, bloqueio, usuario_id))
            conn.commit()
            conn.close()
            return False, "Conta bloqueada por 30 minutos após 5 tentativas incorretas.", False

        cur.execute("UPDATE usuarios SET tentativas_login = %s WHERE id = %s", (novas_tentativas, usuario_id))
        conn.commit()
        conn.close()
        restantes = 5 - novas_tentativas
        return False, f"E-mail ou senha incorretos. {restantes} tentativa(s) restante(s).", False

    except Exception as e:
        return False, f"Erro ao fazer login: {e}", False

def trocar_senha_temporaria(usuario_id, nova_senha):
    try:
        conn = get_conn()
        cur = conn.cursor()
        nova_hash = bcrypt.hashpw(nova_senha.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
        cur.execute("UPDATE usuarios SET senha = %s, senha_temporaria = FALSE WHERE id = %s", (nova_hash, usuario_id))
        conn.commit()
        conn.close()
        return True, "Senha definida com sucesso!"
    except Exception as e:
        return False, f"Erro ao salvar senha: {e}"

@st.dialog("Esqueceu a senha?")
def dialog_recuperar_senha():
    st.caption("Informe seu e-mail cadastrado e enviaremos uma senha temporária.")
    email_rec = st.text_input("E-mail", key="dialog_email_rec")
    if st.button("Enviar senha temporária", use_container_width=True, type="primary"):
        if not email_rec:
            st.error("Informe seu e-mail.")
        else:
            ok, msg = enviar_senha_temporaria(email_rec)
            if ok:
                st.success(msg)
            else:
                st.error(msg)

# --- TELA DE LOGIN / CADASTRO ---
if "usuario_logado" not in st.session_state:
    st.session_state.usuario_logado = None

if "trocar_senha_temp" not in st.session_state:
    st.session_state.trocar_senha_temp = None

# --- TELA DE TROCA DE SENHA TEMPORARIA ---
if st.session_state.trocar_senha_temp:
    u = st.session_state.trocar_senha_temp
    st.title("E-Pro Agent")
    st.warning("Você está usando uma senha temporária. Cadastre uma nova senha para continuar.")
    nova_senha_temp = st.text_input("Nova senha", type="password", key="nova_senha_temp")
    confirma_senha_temp = st.text_input("Confirmar nova senha", type="password", key="confirma_senha_temp")
    if st.button("Salvar e entrar", use_container_width=True, type="primary"):
        if not nova_senha_temp or not confirma_senha_temp:
            st.error("Preencha todos os campos.")
        elif nova_senha_temp != confirma_senha_temp:
            st.error("As senhas não coincidem.")
        elif len(nova_senha_temp) < 6:
            st.error("A senha deve ter pelo menos 6 caracteres.")
        else:
            ok, msg = trocar_senha_temporaria(u["id"], nova_senha_temp)
            if ok:
                st.session_state.trocar_senha_temp = None
                st.session_state.usuario_logado = u
                st.session_state.chats = carregar_chats(u["email"])
                st.session_state.chat_atual = None
                st.session_state.pagina_perfil = False
                st.session_state.prompt_pendente = None
                st.session_state._iniciar_nova_conversa = True
                st.rerun()
            else:
                st.error(msg)
    st.stop()

if st.session_state.usuario_logado is None:
    st.title("E-Pro Agent")
    aba_login, aba_cadastro = st.tabs(["Entrar", "Cadastrar"])

    with aba_login:
        st.subheader("Login")
        email_login = st.text_input("E-mail", key="login_email")
        senha_login = st.text_input("Senha", type="password", key="login_pass")
        _, col_link = st.columns([0.65, 0.35])
        st.markdown('<style>.login-link-col button { border: none !important; background: transparent !important; box-shadow: none !important; color: #888 !important; font-size: 0.8rem !important; text-decoration: underline !important; padding: 0 !important; }</style>', unsafe_allow_html=True)
        with col_link:
            st.markdown('<div class="login-link-col">', unsafe_allow_html=True)
            if st.button("Esqueci minha senha", use_container_width=True, key="btn_esqueceu"):
                dialog_recuperar_senha()
            st.markdown('</div>', unsafe_allow_html=True)
        if st.button("Entrar", use_container_width=True, type="primary"):
            ok, resultado, is_temp = login_usuario_completo(email_login, senha_login)
            if ok:
                if is_temp:
                    st.session_state.trocar_senha_temp = resultado
                    st.rerun()
                else:
                    st.session_state.usuario_logado = resultado
                    st.session_state.chats = carregar_chats(resultado["email"])
                    st.session_state.chat_atual = None
                    st.session_state.pagina_perfil = False
                    st.session_state.prompt_pendente = None
                    st.session_state._iniciar_nova_conversa = True
                    st.rerun()
            else:
                st.error(resultado)

    with aba_cadastro:
        st.subheader("Criar conta")
        nome_cad = st.text_input("Nome completo", key="cad_nome")
        email_cad = st.text_input("E-mail", key="cad_email")
        senha_cad = st.text_input("Senha", type="password", key="cad_pass")
        senha_cad2 = st.text_input("Confirmar senha", type="password", key="cad_pass2")
        if st.button("Cadastrar", use_container_width=True, type="primary"):
            if not all([nome_cad, email_cad, senha_cad, senha_cad2]):
                st.error("Preencha todos os campos.")
            elif senha_cad != senha_cad2:
                st.error("As senhas não coincidem.")
            else:
                ok, msg = cadastrar_usuario(nome_cad, senha_cad, email_cad)
                if ok:
                    st.success(msg + " Faça login para continuar.")
                else:
                    st.error(msg)
    st.stop()

# --- APP PRINCIPAL (USUARIO LOGADO) ---
usuario = st.session_state.usuario_logado

if "pagina_perfil" not in st.session_state:
    st.session_state.pagina_perfil = False

if "pagina_chats" not in st.session_state:
    st.session_state.pagina_chats = 1

if "prompt_pendente" not in st.session_state:
    st.session_state.prompt_pendente = None

CHATS_POR_PAGINA = 10

def nova_conversa():
    id_chat = str(uuid.uuid4())
    st.session_state.chats[id_chat] = {"titulo": "Nova Conversa", "mensagens": [], "fixado": False}
    st.session_state.chat_atual = id_chat
    st.session_state.pagina_perfil = False
    st.session_state.prompt_pendente = None

if "chats" not in st.session_state:
    st.session_state.chats = carregar_chats(usuario["email"])

if st.session_state.get("_iniciar_nova_conversa"):
    st.session_state._iniciar_nova_conversa = False
    nova_conversa()
elif "chat_atual" not in st.session_state or st.session_state.chat_atual is None:
    if st.session_state.chats:
        st.session_state.chat_atual = list(st.session_state.chats.keys())[0]
    else:
        nova_conversa()

# --- SIDEBAR ---
with st.sidebar:
    st.markdown("### E-Pro Agent")
    st.caption(f"Olá, **{usuario['nome']}**")

    col_nova, col_perfil = st.columns([0.75, 0.25])
    if col_nova.button("+ Nova Conversa", use_container_width=True):
        nova_conversa(); st.rerun()
    if col_perfil.button("👤", use_container_width=True, help="Meu Perfil"):
        st.session_state.pagina_perfil = True; st.rerun()

    st.divider()
    st.caption("Conversas Recentes")

    ids_ordenados = sorted(
        st.session_state.chats.keys(),
        key=lambda x: (st.session_state.chats[x].get("fixado", False), x),
        reverse=True
    )
    ids_com_mensagem = [i for i in ids_ordenados if st.session_state.chats[i]["mensagens"]]

    total_paginas = max(1, -(-len(ids_com_mensagem) // CHATS_POR_PAGINA))
    inicio = (st.session_state.pagina_chats - 1) * CHATS_POR_PAGINA
    fim = inicio + CHATS_POR_PAGINA
    ids_pagina = ids_com_mensagem[inicio:fim]

    for id_chat in ids_pagina:
        info = st.session_state.chats[id_chat]
        col_btn, col_menu = st.columns([0.88, 0.12])
        label = f"{'[FIX] ' if info.get('fixado') else ''}{info['titulo'][:20]}"
        tipo = "primary" if id_chat == st.session_state.chat_atual else "secondary"

        if col_btn.button(label, key=f"btn_{id_chat}", use_container_width=True, type=tipo):
            st.session_state.chat_atual = id_chat
            st.session_state.pagina_perfil = False
            st.rerun()

        with col_menu.popover("⋮"):
            if st.button("Fixar / Desafixar", key=f"fix_{id_chat}", use_container_width=True):
                st.session_state.chats[id_chat]["fixado"] = not info.get("fixado", False)
                salvar_chat(id_chat, st.session_state.chats[id_chat], usuario["email"])
                st.rerun()
            if st.button("Excluir", key=f"del_{id_chat}", use_container_width=True, type="primary"):
                deletar_chat(id_chat)
                del st.session_state.chats[id_chat]
                if not st.session_state.chats:
                    nova_conversa()
                else:
                    st.session_state.chat_atual = list(st.session_state.chats.keys())[0]
                st.rerun()

    if total_paginas > 1:
        st.divider()
        col_ant, col_pag, col_prox = st.columns([0.3, 0.4, 0.3])
        if col_ant.button("←", use_container_width=True, disabled=st.session_state.pagina_chats <= 1):
            st.session_state.pagina_chats -= 1; st.rerun()
        col_pag.markdown(f"<div style='text-align:center; padding-top:8px; font-size:0.85rem; color:#aaa;'>{st.session_state.pagina_chats}/{total_paginas}</div>", unsafe_allow_html=True)
        if col_prox.button("→", use_container_width=True, disabled=st.session_state.pagina_chats >= total_paginas):
            st.session_state.pagina_chats += 1; st.rerun()

    st.divider()
    if st.button("Limpar Tudo", use_container_width=True, type="secondary"):
        deletar_todos_chats(usuario["email"])
        st.session_state.chats = {}
        nova_conversa(); st.rerun()
    if st.button("Sair", use_container_width=True):
        st.session_state.usuario_logado = None
        st.session_state.chats = {}
        st.session_state.chat_atual = None
        st.rerun()

# --- PAGINA DE PERFIL ---
if st.session_state.pagina_perfil:
    st.title("Meu Perfil")

    st.subheader("Dados cadastrais")
    novo_nome = st.text_input("Nome completo", value=usuario["nome"])
    novo_email = st.text_input("E-mail", value=usuario["email"])
    if st.button("Salvar alterações", type="primary"):
        ok, msg = atualizar_perfil(usuario["id"], novo_nome, novo_email)
        if ok:
            st.session_state.usuario_logado["nome"] = novo_nome
            st.session_state.usuario_logado["email"] = novo_email
            st.success(msg)
        else:
            st.error(msg)

    st.divider()
    st.subheader("Redefinir senha")
    senha_atual = st.text_input("Senha atual", type="password", key="senha_atual")
    nova_senha = st.text_input("Nova senha", type="password", key="nova_senha")
    confirma_senha = st.text_input("Confirmar nova senha", type="password", key="confirma_senha")
    if st.button("Alterar senha", type="primary"):
        if not all([senha_atual, nova_senha, confirma_senha]):
            st.error("Preencha todos os campos.")
        elif nova_senha != confirma_senha:
            st.error("As senhas não coincidem.")
        else:
            ok, msg = redefinir_senha(usuario["id"], senha_atual, nova_senha)
            if ok:
                st.success(msg)
            else:
                st.error(msg)

    if st.button("← Voltar ao chat"):
        st.session_state.pagina_perfil = False; st.rerun()
    st.stop()

# --- AGENTE E DB ---
db = SQLDatabase.from_uri(st.secrets["NEON_DB_URL"].replace("postgres://", "postgresql://", 1), max_string_length=3000)
llm = ChatGroq(api_key=st.secrets["GROQ_API_KEY"], model_name="llama-3.3-70b-versatile", temperature=0)

PREFIXO_SISTEMA = f"""Voce e um assistente tecnico de suporte focado em SQL.
PRIORIDADE: Responda perguntas de contagem ou status DIRETAMENTE no chat.
REGRA DE EMAIL: Quando o usuario pedir para enviar um relatorio, OBRIGATORIO perguntar: "Posso enviar para o e-mail {usuario['email']} ou gostaria que fosse enviado para outro endereço?". Se o usuario confirmar (responder 'sim', 'pode', 'isso', 'esse mesmo' ou similar), use EXATAMENTE o email {usuario['email']}. Se o usuario informar outro email, use o email informado por ele.
REGRA DE BANCO DE DADOS: A tabela principal SEMPRE se chama 'chamados', mesmo que perguntem sobre "tickets". As colunas sao 'ticket', 'situacao_tarefa', 'solicitante', 'data_abertura' e 'descricao'.
REGRA DE SITUACAO: A coluna 'situacao_tarefa' possui EXATAMENTE estes valores: 'Fechado', 'Pendente DTI', 'Novo', 'Em andamento', 'Agendado', 'Cancelado' e 'Resolvido'. Ao filtrar por situacao, SEMPRE use o valor exato da lista acima. Exemplos de mapeamento: 'agendados' ou 'agendado' = 'Agendado' | 'fechados' ou 'fechado' = 'Fechado' | 'pendentes' = 'Pendente DTI' | 'novos' ou 'novo' = 'Novo' | 'em andamento' = 'Em andamento' | 'cancelados' = 'Cancelado' | 'resolvidos' = 'Resolvido'.
REGRA DE ORDENACAO: Ao listar chamados, SEMPRE ordene pelo campo 'data_abertura' de forma DESCENDENTE (ORDER BY data_abertura DESC), exibindo os mais recentes no topo da lista.
REGRA DE DATAS: OBRIGATORIO: Exiba a data EXATAMENTE como esta no banco, apenas convertendo para o padrao brasileiro (DD/MM/YYYY HH:MM:SS). NUNCA altere a hora (nao diminua nem some horas) e NUNCA fale sobre fuso horario.
REGRA DE BUSCA DE NOMES: Para buscas de pessoas, substitua espaços por '%' e use ILIKE.
REGRA DE FORMATACAO: NUNCA junte resultados na mesma linha. Para listar os tickets, voce DEVE deixar uma linha em branco (duplo Enter) entre cada um deles. Siga ESTRITAMENTE o formato:
Ticket [ticket] - [situacao_tarefa] - [solicitante] - Aberto em [DD/MM/YYYY HH:MM:SS]
REGRA DE DESCRICAO: Quando o usuario pedir a "descricao", detalhes ou o texto de um ticket, OBRIGATORIO trazer o texto INTACTO e COMPLETO do banco de dados. NUNCA resuma, NUNCA corte o texto e NUNCA use reticencias (...).
REGRA DE ENVIO DE EMAIL: Apos confirmar o email de destino, voce DEVE imediatamente chamar a ferramenta 'enviar_relatorio_email' passando o email confirmado e uma nova consulta SQL que busque os dados discutidos na conversa. NUNCA liste os dados novamente antes de enviar.
REGRA DE ABERTOS HOJE: Quando o usuario perguntar quantos chamados "foram abertos hoje" ou "abertos hoje", SEMPRE filtre pela coluna 'data_abertura' usando a data atual (DATE(data_abertura) = CURRENT_DATE). NUNCA filtre por situacao_tarefa nesse caso.
REGRA DE PENDENTES DTI: Quando o usuario perguntar sobre chamados com situacao 'Pendente DTI' (seja pela mensagem pre-definida ou digitando manualmente, independente da forma que escrever), SEMPRE aplique estas restricoes OBRIGATORIAS: (1) Retorne APENAS os campos 'ticket' e 'solicitante', nada mais. (2) Limite SEMPRE a 10 resultados (LIMIT 10). (3) Ordene SEMPRE do mais recente para o mais antigo (ORDER BY data_abertura DESC). (4) Formate como lista simples: "Ticket [numero] - [solicitante]". Se o usuario pedir descricao ou detalhes de 3 ou mais tickets dessa lista, NAO retorne as descricoes e em vez disso pergunte para qual email deve enviar o relatorio completo, seguindo a REGRA DE EMAIL ja estabelecida. Se pedir de 1 ou 2 tickets apenas, pode retornar a descricao normalmente.
REGRA DE COMPARATIVOS: Quando o usuario fizer perguntas comparativas entre periodos (ex: "essa semana vs semana passada", "esse mes vs mes passado", "hoje vs ontem"), execute DUAS queries separadas, uma para cada periodo, e apresente os resultados comparando os valores. Calculos de periodos: hoje = DATE(data_abertura) = CURRENT_DATE | ontem = DATE(data_abertura) = CURRENT_DATE - INTERVAL '1 day' | semana atual = data_abertura >= DATE_TRUNC('week', CURRENT_DATE) AND data_abertura < DATE_TRUNC('week', CURRENT_DATE) + INTERVAL '7 days' | semana passada = data_abertura >= DATE_TRUNC('week', CURRENT_DATE) - INTERVAL '7 days' AND data_abertura < DATE_TRUNC('week', CURRENT_DATE) | mes atual = data_abertura >= DATE_TRUNC('month', CURRENT_DATE) AND data_abertura < DATE_TRUNC('month', CURRENT_DATE) + INTERVAL '1 month' | mes passado = data_abertura >= DATE_TRUNC('month', CURRENT_DATE) - INTERVAL '1 month' AND data_abertura < DATE_TRUNC('month', CURRENT_DATE). OBRIGATORIO: use o label correto para cada periodo (ex: "Hoje/Ontem", "Essa semana/Semana passada", "Esse mes/Mes passado"). Sempre informe a diferenca absoluta e percentual. Exemplo: "Essa semana: 12 chamados | Semana passada: 8 chamados | Diferenca: +4 chamados (+50%)".
REGRA DE BUSCA POR ASSUNTO: Quando o usuario perguntar sobre chamados que tratam de um assunto, tema ou palavra especifica (ex: "chamados sobre agenda", "chamados que falam sobre DOAL", "tickets sobre erro"), siga OBRIGATORIAMENTE este fluxo: ETAPA 1 - Execute APENAS um SELECT COUNT(*) FROM chamados WHERE descricao ILIKE '%palavra%' e informe somente o numero encontrado. PROIBIDO retornar qualquer outro dado ou campo nesta etapa. PROIBIDO chamar enviar_relatorio_email nesta etapa. ETAPA 2 - Apos informar a contagem, pergunte se o usuario deseja receber o relatorio por e-mail seguindo a REGRA DE EMAIL. Somente apos confirmacao do usuario chame enviar_relatorio_email com SELECT * FROM chamados WHERE descricao ILIKE '%palavra%' ORDER BY data_abertura DESC. Se o usuario recusar, responda "Tudo bem! Se precisar de mais alguma informacao, estou por aqui." e PARE.
"""

agente_sql = create_sql_agent(
    llm=llm, db=db, agent_type="tool-calling", verbose=True,
    prefix=PREFIXO_SISTEMA, extra_tools=[enviar_relatorio_email],
    max_iterations=10, handle_parsing_errors=True,
    return_intermediate_steps=True
)

# --- AREA DO CHAT ---
chat_info = st.session_state.chats[st.session_state.chat_atual]

SUGESTOES = [
    "Quantos chamados foram abertos hoje?",
    "Resumo dos chamados Pendentes DTI",
    "Quais chamados estão agendados?",
    "Quais chamados estão em andamento?",
]

# Saudacao e sugestoes apenas em chats vazios
if not chat_info["mensagens"]:
    st.markdown(f"""
        <div class="saudacao-container">
            <div class="saudacao-texto">{get_saudacao()}, {usuario['nome'].split()[0]}!</div>
        </div>
    """, unsafe_allow_html=True)

    col1, col2 = st.columns(2)
    for i, sugestao in enumerate(SUGESTOES):
        col = col1 if i % 2 == 0 else col2
        if col.button(sugestao, use_container_width=True, key=f"sugestao_{i}"):
            st.session_state.prompt_pendente = sugestao
            st.rerun()
else:
    for msg in chat_info["mensagens"]:
        avatar = "👤" if msg["role"] == "user" else "🤖"
        with st.chat_message(msg["role"], avatar=avatar):
            st.markdown(msg["content"])

# --- CAPTURA DO PROMPT (digitado ou via sugestao) ---
prompt_digitado = st.chat_input("Como posso ajudar você hoje?")
if prompt_digitado:
    prompt = prompt_digitado
elif st.session_state.prompt_pendente:
    prompt = st.session_state.prompt_pendente
    st.session_state.prompt_pendente = None
else:
    prompt = None

# --- PROCESSAMENTO DO CHAT ---
if prompt:
    chat_info["mensagens"].append({"role": "user", "content": prompt})
    with st.chat_message("user", avatar="👤"):
        st.markdown(prompt)

    with st.chat_message("assistant", avatar="🤖"):
        indicador = st.empty()
        indicador.markdown("""
            <div style="display:flex; align-items:center; gap:5px; padding: 4px 0;">
                <span style="font-size:0.9rem; color:#888;">Analisando</span>
                <span style="display:inline-flex; gap:3px;">
                    <span style="width:6px;height:6px;border-radius:50%;background:#888;animation:bounce 1.2s infinite ease-in-out;animation-delay:0s;"></span>
                    <span style="width:6px;height:6px;border-radius:50%;background:#888;animation:bounce 1.2s infinite ease-in-out;animation-delay:0.2s;"></span>
                    <span style="width:6px;height:6px;border-radius:50%;background:#888;animation:bounce 1.2s infinite ease-in-out;animation-delay:0.4s;"></span>
                </span>
            </div>
            <style>
            @keyframes bounce {
                0%, 80%, 100% { transform: translateY(0); opacity: 0.4; }
                40% { transform: translateY(-6px); opacity: 1; }
            }
            </style>
        """, unsafe_allow_html=True)

        historico_contexto = " | ".join([m['content'] for m in chat_info["mensagens"][-12:]])

        # --- ROTEADOR DE EMAIL: intercepta pedido antes de chamar o agente ---
        palavras_envio = ["enviar", "manda", "mande", "relatório", "relatorio", "report"]
        palavras_confirmacao = ["sim", "pode", "isso", "esse mesmo", "pode enviar", "outro", "@"]
        palavras_recusa = ["não precisa", "nao precisa", "não", "nao", "deixa", "tanto faz", "pode não", "pode nao"]
        palavras_busca_assunto = ["falam sobre", "fala sobre", "tratam de", "trata de", "relacionados a", "relacionado a", "mencionam", "menciona", "sobre o assunto", "com a palavra", "contém", "contem"]
        ultimo_bot = next((m['content'] for m in reversed(chat_info["mensagens"][:-1]) if m['role'] == "assistant"), "")
        ja_perguntou_email = "posso enviar para o e-mail" in ultimo_bot.lower()
        ultimo_bot_foi_contagem = any(x in ultimo_bot.lower() for x in ["chamados que falam", "chamados encontrados", "foram encontrados", "chamados com"])
        prompt_lower = prompt.lower()
        usuario_recusou = any(p in prompt_lower for p in palavras_recusa)
        usuario_confirmou = any(p in prompt_lower for p in palavras_confirmacao) and not any(p in prompt_lower for p in palavras_envio)
        pedido_envio = any(p in prompt_lower for p in palavras_envio)
        busca_por_assunto = any(p in prompt_lower for p in palavras_busca_assunto)

        # Intercepta recusa quando o bot já perguntou sobre email
        if (ja_perguntou_email or ultimo_bot_foi_contagem) and usuario_recusou:
            texto_final = "Tudo bem! Se precisar de mais alguma informação, estou por aqui."
            indicador.empty()
            st.markdown(texto_final)
            chat_info["mensagens"].append({"role": "assistant", "content": texto_final})
            salvar_chat(st.session_state.chat_atual, chat_info, usuario["email"])
            st.stop()

        # Intercepta busca por assunto/palavra-chave na descricao
        if busca_por_assunto and not ja_perguntou_email:
            import re
            # Extrai a palavra-chave da pergunta
            for p in palavras_busca_assunto:
                if p in prompt_lower:
                    idx = prompt_lower.index(p) + len(p)
                    palavra_chave = prompt[idx:].strip().rstrip("?!.,").strip()
                    break
            try:
                conn = get_conn()
                cur = conn.cursor()
                cur.execute("SELECT COUNT(*) FROM chamados WHERE descricao ILIKE %s", (f"%{palavra_chave}%",))
                contagem = cur.fetchone()[0]
                conn.close()
                if contagem == 0:
                    texto_final = f"Não encontrei nenhum chamado que mencione \"{palavra_chave}\". Tente usar uma palavra diferente."
                else:
                    texto_final = f"Encontrei **{contagem}** chamados que mencionam \"{palavra_chave}\". Posso enviar para o e-mail **{usuario['email']}** ou gostaria que fosse enviado para outro endereço?"
            except Exception as e:
                texto_final = "Tive um problema ao buscar esses dados. Pode tentar reformular a pergunta?"
            indicador.empty()
            st.markdown(texto_final)
            chat_info["mensagens"].append({"role": "assistant", "content": texto_final})
            salvar_chat(st.session_state.chat_atual, chat_info, usuario["email"])
            st.stop()

        if pedido_envio and not ja_perguntou_email and not usuario_confirmou:
            texto_final = f"Posso enviar para o e-mail **{usuario['email']}** ou gostaria que fosse enviado para outro endereço?"
            indicador.empty()
            st.markdown(texto_final)
            chat_info["mensagens"].append({"role": "assistant", "content": texto_final})
            salvar_chat(st.session_state.chat_atual, chat_info, usuario["email"])
            st.stop()

        prompt_classificador = f"""
        Analise a conversa recente: [{historico_contexto}]
        A última mensagem do usuario requer buscar dados, continuacao sobre um ticket/chamado, detalhes, relatorios ou confirmacao de envio de email? Responda APENAS 'SQL'.
        Se for EXCLUSIVAMENTE uma saudacao ou bate-papo generico (ex: 'oi', 'tudo bem', 'como vai', 'obrigado'), responda APENAS 'CHAT'.
        """
        intencao = llm.invoke(prompt_classificador).content.strip().upper()

        if "CHAT" in intencao:
            prompt_chat = f"Voce é o E-Pro Agent. Responda de forma natural e amigavel a interacao: '{prompt}'"
            texto_final = llm.invoke(prompt_chat).content.strip()
        else:
            try:
                historico = "\n".join([f"{m['role']}: {m['content']}" for m in chat_info["mensagens"][-12:]])
                input_final = f"HISTORICO:\n{historico}\n\nPERGUNTA: {prompt}\n(Vá direto ao ponto e use SQL rapido)"

                res = agente_sql.invoke({"input": input_final})

                steps_str = str(res.get("intermediate_steps", ""))
                email_enviado = "Sucesso total" in steps_str or "ja foi enviado" in steps_str

                if email_enviado:
                    texto_final = "E-mail enviado, favor verificar sua caixa de emails"
                else:
                    texto_final = res["output"]
                    if "Agent stopped due to max iterations" in texto_final:
                        texto_final = "A consulta ficou muito complexa e eu precisei parar. Pode tentar fazer a pergunta de uma forma mais simples?"

            except Exception as e:
                steps_str = str(e)
                if "Sucesso total" in steps_str or "ja foi enviado" in steps_str:
                    texto_final = "E-mail enviado, favor verificar sua caixa de emails"
                elif "max iterations" in steps_str.lower():
                    texto_final = "A consulta demorou demais. Pode tentar reformular a pergunta?"
                else:
                    texto_final = "Tive um problema tecnico ao buscar esses dados. Pode tentar reformular a pergunta?"

        indicador.empty()
        st.markdown(texto_final)
        chat_info["mensagens"].append({"role": "assistant", "content": texto_final})

    salvar_chat(st.session_state.chat_atual, chat_info, usuario["email"])

    # --- LOGICA DE TITULO ---
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

        salvar_chat(st.session_state.chat_atual, chat_info, usuario["email"])
        st.rerun()