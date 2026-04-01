import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
import streamlit as st
from langchain.tools import tool
import pandas as pd
import psycopg2
import io
import time
import re

# Controle global para evitar envios duplicados
_ultimo_envio = {}

def limpar_descricao(texto):
    if not texto or not isinstance(texto, str):
        return texto
    match_assunto = re.search(r'Assunto:', texto, re.IGNORECASE)
    if match_assunto:
        texto = texto[match_assunto.start():]
    cortes = [
        r'[\n\s]Att\.[\s,|]', r'[\n\s]Atenciosamente',
        r'\nAtt,', r'\| [A-Z][a-z]+ [A-Z][a-z]+',
        r'\nPraça ', r'\nRua ', r'\nAv\.',
        r'\nTel:', r'\nFone:', r'\nwww\.', r'\nhttp',
        r' Att\.,', r' Atenciosamente,',
    ]
    for padrao in cortes:
        match = re.search(padrao, texto)
        if match:
            texto = texto[:match.start()]
    texto = re.sub(r'[ \t]{2,}', ' ', texto)
    texto = re.sub(r'\n{3,}', '\n\n', texto)
    return texto.strip()

@tool
def enviar_relatorio_email(email_destino: str, consulta_sql: str) -> str:
    """
    Ferramenta para enviar relatorios de chamados.
    Recebe o email_destino e a consulta_sql. Executa a consulta no banco de dados, 
    gera um arquivo CSV com os resultados e envia em anexo para o email.
    O email_destino deve ser fornecido obrigatoriamente pelo usuario na conversa.
    NUNCA passe os dados brutos, passe apenas a string da consulta SQL.
    """
    global _ultimo_envio

    # --- TRAVA DE SEGURANCA: VALIDACAO DE EMAIL ---
    placeholders = ["example.com", "seu_email", "email_aqui", "user@"]
    if any(p in email_destino.lower() for p in placeholders) or "@" not in email_destino:
        return "ERRO: O email fornecido parece ser ficticio ou invalido. PARE a execucao e pergunte o email real do usuario agora."

    # --- TRAVA DE SEGURANCA: VALIDACAO DE SQL ---
    if not consulta_sql.strip().lstrip('\n\r\t ').upper().startswith("SELECT"):
        return "ERRO: Apenas consultas SELECT sao permitidas para gerar relatorios."

    # --- TRAVA CONTRA ENVIO DUPLICADO ---
    agora = time.time()
    chave = f"{email_destino}_{consulta_sql[:50]}"
    if agora - _ultimo_envio.get(chave, 0) < 15:
        return f"Sucesso total: O relatorio ja foi enviado para {email_destino}. Tarefa concluida, informe o usuario."
    _ultimo_envio[chave] = agora

    try:
        # 1. Conecta no banco de dados e executa a query recebida da IA
        db_url = st.secrets["NEON_DB_URL"]
        if db_url.startswith("postgres://"):
            db_url = db_url.replace("postgres://", "postgresql://", 1)
            
        conn = psycopg2.connect(db_url)
        df = pd.read_sql_query(consulta_sql, conn)
        conn.close()

        if df.empty:
            return "A consulta nao retornou nenhum chamado. O e-mail nao foi enviado. Informe isso ao usuario."

        # 2. Remove colunas desnecessarias e formata datas
        colunas_remover = [c for c in ['origem', 'grupo', 'tipo_demanda'] if c in df.columns]
        if colunas_remover:
            df = df.drop(columns=colunas_remover)

        # Limpa descrição e solução
        if 'descricao' in df.columns:
            df['descricao'] = df['descricao'].apply(limpar_descricao)
        if 'solucao_resposta' in df.columns:
            df['solucao_resposta'] = df['solucao_resposta'].apply(limpar_descricao)

        if 'descricao' in df.columns:
            df['descricao'] = df['descricao'].apply(limpar_descricao)

        for col in df.select_dtypes(include=['datetime64[ns]', 'datetime64[ns, UTC]']).columns:
            df[col] = df[col].dt.strftime('%d/%m/%Y %H:%M:%S')

        # 3. Converte o resultado para um CSV em memoria
        csv_buffer = io.StringIO()
        df.to_csv(csv_buffer, index=False, sep=';', encoding='utf-8-sig')
        csv_bytes = csv_buffer.getvalue().encode('utf-8-sig')

        # 3. Puxa as credenciais
        remetente = st.secrets["EMAIL_REMETENTE"]
        senha = st.secrets["SENHA_APP_EMAIL"]

        # 4. Monta o e-mail
        mensagem = MIMEMultipart()
        mensagem["From"] = remetente
        mensagem["To"] = email_destino
        mensagem["Subject"] = "Relatorio de Chamados 4Biz - Assistente IA"

        corpo_email = f"Ola,\n\nSegue em anexo o relatorio contendo {len(df)} chamados solicitados via chat.\n\nAtenciosamente,\nAssistente E-pro"
        mensagem.attach(MIMEText(corpo_email, "plain", "utf-8"))

        # 5. Anexa o CSV
        anexo = MIMEApplication(csv_bytes, _subtype="csv")
        anexo.add_header('Content-Disposition', 'attachment', filename='relatorio_chamados.csv')
        mensagem.attach(anexo)

        # 6. Disparo via SMTP com timeout de 10 segundos
        servidor = smtplib.SMTP("smtp.gmail.com", 587, timeout=10)
        servidor.starttls()
        servidor.login(remetente, senha)
        servidor.send_message(mensagem)
        servidor.quit()

        return f"Sucesso total: O relatorio com {len(df)} chamados foi enviado para {email_destino}. Tarefa concluida, informe o usuario."

    except Exception as e:
        return f"Erro critico ao processar relatorio: {str(e)}"