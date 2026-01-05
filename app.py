from flask import Flask, render_template, request, jsonify, redirect, url_for, send_file
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
from sqlalchemy import func
import os
import socket
import qrcode
import io
import base64
import pandas as pd
from werkzeug.utils import secure_filename
import webbrowser
import threading

# Configuração do Flask
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///energia.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'sua-chave-secreta-aqui-2026'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # Limite de 16MB para upload
app.config['UPLOAD_FOLDER'] = 'uploads'

# Cria pasta de uploads se não existir
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Inicialização do SQLAlchemy
db = SQLAlchemy(app)


# ========================================
# MODELOS
# ========================================

class Quadro(db.Model):
    """Modelo para representar um quadro de energia/medidor"""
    __tablename__ = 'quadros'
    
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    localizacao = db.Column(db.String(200), nullable=False)
    ativo = db.Column(db.Boolean, default=True, nullable=False)
    
    # Relacionamento com leituras
    leituras = db.relationship('Leitura', backref='quadro', lazy=True, cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<Quadro {self.nome}>'
    
    def to_dict(self):
        """Converte o objeto para dicionário"""
        return {
            'id': self.id,
            'nome': self.nome,
            'localizacao': self.localizacao,
            'ativo': self.ativo
        }


class Leitura(db.Model):
    """Modelo para representar uma leitura de medidor"""
    __tablename__ = 'leituras'
    
    id = db.Column(db.Integer, primary_key=True)
    quadro_id = db.Column(db.Integer, db.ForeignKey('quadros.id'), nullable=False)
    data_registro = db.Column(db.DateTime, default=datetime.now, nullable=False)
    valor_leitura = db.Column(db.Float, nullable=False)
    consumo_dia = db.Column(db.Float, nullable=True)
    alerta_reset = db.Column(db.Boolean, default=False, nullable=False)
    
    def __repr__(self):
        return f'<Leitura {self.id} - Quadro {self.quadro_id}>'
    
    def to_dict(self):
        """Converte o objeto para dicionário"""
        return {
            'id': self.id,
            'quadro_id': self.quadro_id,
            'quadro_nome': self.quadro.nome if self.quadro else None,
            'data_registro': self.data_registro.strftime('%d/%m/%Y %H:%M:%S'),
            'valor_leitura': self.valor_leitura,
            'consumo_dia': self.consumo_dia,
            'alerta_reset': self.alerta_reset
        }


class LeituraRascunho(db.Model):
    """Modelo para representar leituras temporárias/rascunho antes da validação final"""
    __tablename__ = 'leituras_rascunho'
    
    id = db.Column(db.Integer, primary_key=True)
    quadro_id = db.Column(db.Integer, db.ForeignKey('quadros.id'), nullable=False)
    data_registro = db.Column(db.DateTime, default=datetime.now, nullable=False)
    valor_leitura = db.Column(db.Float, nullable=False)
    consumo_provisorio = db.Column(db.Float, nullable=True)
    alerta_reset = db.Column(db.Boolean, default=False, nullable=False)
    
    # Relacionamento
    quadro = db.relationship('Quadro', backref='leituras_rascunho', lazy=True)
    
    def __repr__(self):
        return f'<LeituraRascunho {self.id} - Quadro {self.quadro_id}>'
    
    def to_dict(self):
        """Converte o objeto para dicionário"""
        return {
            'id': self.id,
            'quadro_id': self.quadro_id,
            'quadro_nome': self.quadro.nome if self.quadro else None,
            'quadro_localizacao': self.quadro.localizacao if self.quadro else None,
            'data_registro': self.data_registro.strftime('%d/%m/%Y %H:%M:%S'),
            'valor_leitura': self.valor_leitura,
            'consumo_provisorio': self.consumo_provisorio,
            'alerta_reset': self.alerta_reset
        }


class SessaoLeitura(db.Model):
    """Modelo para controlar sessões de leitura ativas"""
    __tablename__ = 'sessoes_leitura'
    
    id = db.Column(db.Integer, primary_key=True)
    ativa = db.Column(db.Boolean, default=True, nullable=False)
    data_inicio = db.Column(db.DateTime, default=datetime.now, nullable=False)
    data_fim = db.Column(db.DateTime, nullable=True)
    iniciada_por = db.Column(db.String(100), default='Supervisor', nullable=False)
    
    def __repr__(self):
        return f'<SessaoLeitura {self.id} - Ativa: {self.ativa}>'
    
    def to_dict(self):
        """Converte o objeto para dicionário"""
        return {
            'id': self.id,
            'ativa': self.ativa,
            'data_inicio': self.data_inicio.strftime('%d/%m/%Y %H:%M:%S'),
            'data_fim': self.data_fim.strftime('%d/%m/%Y %H:%M:%S') if self.data_fim else None,
            'iniciada_por': self.iniciada_por
        }


# ========================================
# FUNÇÕES DE INICIALIZAÇÃO
# ========================================

def inicializar_banco():
    """Cria as tabelas no banco de dados"""
    with app.app_context():
        db.create_all()
        print("✅ Banco de dados inicializado!")
        popular_dados_exemplo()


def popular_dados_exemplo():
    """Popula o banco com quadros de exemplo se estiver vazio"""
    if Quadro.query.count() == 0:
        quadros_exemplo = [
            Quadro(nome='Galpão A', localizacao='Área de Produção', ativo=True),
            Quadro(nome='Escritório', localizacao='Prédio Administrativo', ativo=True),
            Quadro(nome='Recepção', localizacao='Entrada Principal', ativo=True)
        ]
        
        for quadro in quadros_exemplo:
            db.session.add(quadro)
        
        db.session.commit()
        print("✅ Dados de exemplo criados:")
        for quadro in quadros_exemplo:
            print(f"   - {quadro.nome} ({quadro.localizacao})")


# ========================================
# FUNÇÕES AUXILIARES
# ========================================

def obter_ip_local():
    """Descobre o IP local da máquina na rede"""
    try:
        # Cria um socket temporário para descobrir o IP
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))  # Conecta a um servidor externo (não envia dados)
        ip_local = s.getsockname()[0]
        s.close()
        return ip_local
    except Exception:
        return "127.0.0.1"  # Fallback para localhost


def gerar_qrcode(url):
    """Gera um QR Code em base64 para uma URL"""
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(url)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    
    # Converte para base64
    buffer = io.BytesIO()
    img.save(buffer, format='PNG')
    buffer.seek(0)
    img_base64 = base64.b64encode(buffer.getvalue()).decode()
    
    return f"data:image/png;base64,{img_base64}"


def calcular_consumo_total_hoje():
    """Calcula o consumo total de todos os quadros hoje"""
    hoje = datetime.now().date()
    inicio_dia = datetime.combine(hoje, datetime.min.time())
    fim_dia = datetime.combine(hoje, datetime.max.time())
    
    consumo_total = db.session.query(func.sum(Leitura.consumo_dia))\
        .filter(Leitura.data_registro >= inicio_dia)\
        .filter(Leitura.data_registro <= fim_dia)\
        .filter(Leitura.consumo_dia.isnot(None))\
        .scalar()
    
    return consumo_total if consumo_total else 0


def calcular_media_ultimos_3_meses():
    """Calcula a média de consumo dos últimos 3 meses"""
    tres_meses_atras = datetime.now() - timedelta(days=90)
    
    consumo_total = db.session.query(func.sum(Leitura.consumo_dia))\
        .filter(Leitura.data_registro >= tres_meses_atras)\
        .filter(Leitura.consumo_dia.isnot(None))\
        .scalar()
    
    if consumo_total:
        return consumo_total / 90  # Média diária
    return 0


def obter_status_quadros():
    """Retorna informações de status de todos os quadros"""
    quadros = Quadro.query.filter_by(ativo=True).all()
    status_list = []
    
    hoje = datetime.now().date()
    inicio_dia = datetime.combine(hoje, datetime.min.time())
    
    for quadro in quadros:
        # Busca última leitura
        ultima_leitura = Leitura.query.filter_by(quadro_id=quadro.id)\
            .order_by(Leitura.data_registro.desc()).first()
        
        # Busca leitura de hoje
        leitura_hoje = Leitura.query.filter_by(quadro_id=quadro.id)\
            .filter(Leitura.data_registro >= inicio_dia)\
            .order_by(Leitura.data_registro.desc()).first()
        
        status = {
            'id': quadro.id,
            'nome': quadro.nome,
            'localizacao': quadro.localizacao,
            'valor_atual': ultima_leitura.valor_leitura if ultima_leitura else 0,
            'consumo_hoje': leitura_hoje.consumo_dia if leitura_hoje and leitura_hoje.consumo_dia else 0,
            'status': 'OK' if leitura_hoje else 'Pendente',
            'ultima_data': ultima_leitura.data_registro.strftime('%d/%m/%Y %H:%M') if ultima_leitura else 'Nunca',
            'alerta_reset': ultima_leitura.alerta_reset if ultima_leitura else False
        }
        
        status_list.append(status)
    
    return status_list


# ========================================
# ROTAS
# ========================================

@app.route('/')
def index():
    """Dashboard principal com QR Code para acesso mobile"""
    # Obtém IP local e gera QR Code
    ip_local = obter_ip_local()
    url_mobile = f"http://{ip_local}:5000/registrar"
    qrcode_img = gerar_qrcode(url_mobile)
    
    # Calcula métricas
    consumo_hoje = calcular_consumo_total_hoje()
    media_3_meses = calcular_media_ultimos_3_meses()
    status_quadros = obter_status_quadros()
    
    # Conta rascunhos pendentes
    total_rascunhos = LeituraRascunho.query.count()
    
    return render_template('dashboard.html',
                         qrcode_img=qrcode_img,
                         url_mobile=url_mobile,
                         ip_local=ip_local,
                         consumo_hoje=consumo_hoje,
                         media_3_meses=media_3_meses,
                         status_quadros=status_quadros,
                         total_rascunhos=total_rascunhos)


@app.route('/registrar', methods=['GET', 'POST'])
def registrar():
    """Rota principal para registro de leituras em RASCUNHO"""
    
    # Verifica se há sessão ativa
    sessao_ativa = SessaoLeitura.query.filter_by(ativa=True).first()
    
    if request.method == 'GET':
        # Renderiza template independente do status da sessão
        # O JavaScript no template fará o bloqueio visual se necessário
        return render_template('mobile_form.html', sessao_ativa=(sessao_ativa is not None))
    
    elif request.method == 'POST':
        # Bloqueia registro se não houver sessão ativa
        if not sessao_ativa:
            return jsonify({
                'sucesso': False,
                'erro': 'Não há sessão ativa. Aguarde o supervisor iniciar uma sessão de leitura.'
            }), 403
        
        # Recebe dados do formulário
        try:
            quadro_id = request.form.get('quadro_id', type=int)
            novo_valor = request.form.get('novo_valor', type=float)
            
            if not quadro_id or novo_valor is None:
                return jsonify({
                    'sucesso': False,
                    'erro': 'Dados incompletos. Informe o quadro e o valor da leitura.'
                }), 400
            
            # Verifica se o quadro existe
            quadro = Quadro.query.get(quadro_id)
            if not quadro:
                return jsonify({
                    'sucesso': False,
                    'erro': 'Quadro não encontrado.'
                }), 404
            
            # Busca a última leitura OFICIAL (da tabela Leitura)
            ultima_leitura_oficial = Leitura.query.filter_by(quadro_id=quadro_id)\
                .order_by(Leitura.data_registro.desc()).first()
            
            # Calcula o consumo provisório
            consumo_provisorio = 0
            alerta_reset = False
            
            if ultima_leitura_oficial:
                valor_anterior = ultima_leitura_oficial.valor_leitura
                
                if novo_valor >= valor_anterior:
                    # Consumo normal
                    consumo_provisorio = novo_valor - valor_anterior
                else:
                    # INCONSISTÊNCIA DETECTADA: valor menor que o anterior
                    return jsonify({
                        'sucesso': False,
                        'inconsistencia': True,
                        'valor_anterior': valor_anterior,
                        'novo_valor': novo_valor,
                        'quadro_nome': quadro.nome,
                        'mensagem': 'O valor informado é MENOR que a leitura anterior. O relógio do medidor virou?'
                    }), 409  # 409 = Conflict
            
            # Verifica se já existe um rascunho para este quadro
            rascunho_existente = LeituraRascunho.query.filter_by(quadro_id=quadro_id).first()
            
            if rascunho_existente:
                # Atualiza o rascunho existente
                rascunho_existente.valor_leitura = novo_valor
                rascunho_existente.consumo_provisorio = consumo_provisorio
                rascunho_existente.alerta_reset = alerta_reset
                rascunho_existente.data_registro = datetime.now()
            else:
                # Cria novo rascunho
                rascunho_existente = LeituraRascunho(
                    quadro_id=quadro_id,
                    valor_leitura=novo_valor,
                    consumo_provisorio=consumo_provisorio,
                    alerta_reset=alerta_reset
                )
                db.session.add(rascunho_existente)
            
            db.session.commit()
            
            return jsonify({
                'sucesso': True,
                'mensagem': f'Leitura registrada no RASCUNHO!',
                'leitura': rascunho_existente.to_dict(),
                'tipo': 'rascunho'
            }), 201
            
        except ValueError:
            return jsonify({
                'sucesso': False,
                'erro': 'Valor inválido. Certifique-se de inserir um número válido.'
            }), 400
        except Exception as e:
            db.session.rollback()
            return jsonify({
                'sucesso': False,
                'erro': f'Erro ao processar leitura: {str(e)}'
            }), 500


@app.route('/confirmar_reset', methods=['POST'])
def confirmar_reset():
    """Confirma e salva leitura em RASCUNHO quando o usuário confirma que o medidor virou"""
    try:
        quadro_id = request.form.get('quadro_id', type=int)
        novo_valor = request.form.get('novo_valor', type=float)
        
        if not quadro_id or novo_valor is None:
            return jsonify({
                'sucesso': False,
                'erro': 'Dados incompletos.'
            }), 400
        
        # Verifica se o quadro existe
        quadro = Quadro.query.get(quadro_id)
        if not quadro:
            return jsonify({
                'sucesso': False,
                'erro': 'Quadro não encontrado.'
            }), 404
        
        # Verifica se já existe um rascunho para este quadro
        rascunho_existente = LeituraRascunho.query.filter_by(quadro_id=quadro_id).first()
        
        if rascunho_existente:
            # Atualiza o rascunho existente
            rascunho_existente.valor_leitura = novo_valor
            rascunho_existente.consumo_provisorio = novo_valor  # Considera o novo valor como consumo total
            rascunho_existente.alerta_reset = True
            rascunho_existente.data_registro = datetime.now()
        else:
            # Cria novo rascunho com alerta de reset
            rascunho_existente = LeituraRascunho(
                quadro_id=quadro_id,
                valor_leitura=novo_valor,
                consumo_provisorio=novo_valor,  # Considera o novo valor como consumo total
                alerta_reset=True  # Marca que houve reset/virada do medidor
            )
            db.session.add(rascunho_existente)
        
        db.session.commit()
        
        return jsonify({
            'sucesso': True,
            'mensagem': f'Leitura com RESET registrada no RASCUNHO!',
            'leitura': rascunho_existente.to_dict(),
            'tipo': 'rascunho'
        }), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'sucesso': False,
            'erro': f'Erro ao confirmar reset: {str(e)}'
        }), 500


@app.route('/iniciar_contagem', methods=['POST'])
def iniciar_contagem():
    """Limpa a tabela de rascunhos para iniciar uma nova contagem do dia"""
    try:
        # Conta quantos rascunhos existem
        total_rascunhos = LeituraRascunho.query.count()
        
        # Limpa todos os rascunhos
        LeituraRascunho.query.delete()
        db.session.commit()
        
        return jsonify({
            'sucesso': True,
            'mensagem': f'Nova contagem iniciada! {total_rascunhos} rascunho(s) removido(s).'
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'sucesso': False,
            'erro': f'Erro ao iniciar contagem: {str(e)}'
        }), 500


@app.route('/revisao')
def revisao():
    """Tela de revisão e validação dos rascunhos antes da consolidação final"""
    # Busca todos os rascunhos
    rascunhos = LeituraRascunho.query.all()
    
    # Prepara dados com análise de desvios
    dados_revisao = []
    
    for rascunho in rascunhos:
        # Calcula média de consumo dos últimos 90 dias deste quadro
        noventa_dias_atras = datetime.now() - timedelta(days=90)
        
        media_90_dias = db.session.query(func.avg(Leitura.consumo_dia))\
            .filter(Leitura.quadro_id == rascunho.quadro_id)\
            .filter(Leitura.data_registro >= noventa_dias_atras)\
            .filter(Leitura.consumo_dia.isnot(None))\
            .scalar()
        
        media_90_dias = media_90_dias if media_90_dias else 0
        
        # Busca o último valor registrado oficialmente
        ultima_leitura_oficial = Leitura.query.filter_by(quadro_id=rascunho.quadro_id)\
            .order_by(Leitura.data_registro.desc()).first()
        
        ultimo_valor_oficial = ultima_leitura_oficial.valor_leitura if ultima_leitura_oficial else 0
        ultima_data_oficial = ultima_leitura_oficial.data_registro.strftime('%d/%m/%Y %H:%M') if ultima_leitura_oficial else 'Nunca'
        
        # Calcula desvio percentual
        desvio_percentual = 0
        status_desvio = 'normal'
        
        if media_90_dias > 0 and rascunho.consumo_provisorio:
            desvio_percentual = ((rascunho.consumo_provisorio - media_90_dias) / media_90_dias) * 100
            
            if abs(desvio_percentual) > 50:
                status_desvio = 'critico'  # Vermelho
            elif abs(desvio_percentual) > 30:
                status_desvio = 'alerta'   # Amarelo
        
        dados_revisao.append({
            'id': rascunho.id,
            'quadro_id': rascunho.quadro_id,
            'quadro_nome': rascunho.quadro.nome,
            'quadro_localizacao': rascunho.quadro.localizacao,
            'valor_leitura': rascunho.valor_leitura,
            'consumo_provisorio': rascunho.consumo_provisorio,
            'alerta_reset': rascunho.alerta_reset,
            'media_90_dias': round(media_90_dias, 2),
            'desvio_percentual': round(desvio_percentual, 1),
            'status_desvio': status_desvio,
            'ultimo_valor_oficial': round(ultimo_valor_oficial, 2),
            'ultima_data_oficial': ultima_data_oficial
        })    
    
    # Variáveis para a sidebar
    ip_local = obter_ip_local()
    url_mobile = f"http://{ip_local}:5000/registrar"
    qrcode_img = gerar_qrcode(url_mobile)
    total_rascunhos = len(dados_revisao)
    
    return render_template('revisao.html', 
                         dados_revisao=dados_revisao,
                         qrcode_img=qrcode_img,
                         ip_local=ip_local,
                         total_rascunhos=total_rascunhos)


@app.route('/revisao/editar/<int:id>', methods=['POST'])
def editar_rascunho(id):
    """Edita um rascunho específico"""
    try:
        rascunho = LeituraRascunho.query.get(id)
        
        if not rascunho:
            return jsonify({
                'sucesso': False,
                'erro': 'Rascunho não encontrado.'
            }), 404
        
        novo_valor = request.form.get('valor_leitura', type=float)
        
        if novo_valor is None:
            return jsonify({
                'sucesso': False,
                'erro': 'Valor da leitura é obrigatório.'
            }), 400
        
        # Busca última leitura oficial para recalcular consumo
        ultima_oficial = Leitura.query.filter_by(quadro_id=rascunho.quadro_id)\
            .order_by(Leitura.data_registro.desc()).first()
        
        # Recalcula consumo provisório
        if ultima_oficial:
            if novo_valor >= ultima_oficial.valor_leitura:
                rascunho.consumo_provisorio = novo_valor - ultima_oficial.valor_leitura
                rascunho.alerta_reset = False
            else:
                # Valor menor - marca como reset
                rascunho.consumo_provisorio = novo_valor
                rascunho.alerta_reset = True
        else:
            rascunho.consumo_provisorio = 0
            rascunho.alerta_reset = False
        
        rascunho.valor_leitura = novo_valor
        rascunho.data_registro = datetime.now()
        
        db.session.commit()
        
        return jsonify({
            'sucesso': True,
            'mensagem': 'Rascunho atualizado com sucesso!',
            'rascunho': rascunho.to_dict()
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'sucesso': False,
            'erro': f'Erro ao editar rascunho: {str(e)}'
        }), 500


@app.route('/verificar_conflitos', methods=['GET'])
def verificar_conflitos():
    """Verifica se há conflitos de data antes de consolidar"""
    try:
        rascunhos = LeituraRascunho.query.all()
        
        if not rascunhos:
            return jsonify({
                'sucesso': False,
                'erro': 'Não há rascunhos para verificar.'
            }), 400
        
        conflitos = []
        
        for rascunho in rascunhos:
            # Busca leitura oficial do mesmo quadro no mesmo DIA (ignora hora)
            data_rascunho = rascunho.data_registro.date()
            
            leitura_existente = Leitura.query.filter(
                Leitura.quadro_id == rascunho.quadro_id,
                db.func.date(Leitura.data_registro) == data_rascunho
            ).first()
            
            if leitura_existente:
                conflitos.append({
                    'rascunho_id': rascunho.id,
                    'quadro_nome': rascunho.quadro.nome,
                    'quadro_localizacao': rascunho.quadro.localizacao,
                    'rascunho_data': rascunho.data_registro.strftime('%d/%m/%Y às %H:%M'),
                    'rascunho_valor': rascunho.valor_leitura,
                    'existente_id': leitura_existente.id,
                    'existente_data': leitura_existente.data_registro.strftime('%d/%m/%Y às %H:%M'),
                    'existente_valor': leitura_existente.valor_leitura
                })
        
        return jsonify({
            'sucesso': True,
            'tem_conflitos': len(conflitos) > 0,
            'conflitos': conflitos,
            'total_rascunhos': len(rascunhos)
        }), 200
        
    except Exception as e:
        return jsonify({
            'sucesso': False,
            'erro': f'Erro ao verificar conflitos: {str(e)}'
        }), 500


@app.route('/consolidar', methods=['POST'])
def consolidar():
    """Consolida todos os rascunhos, movendo para a tabela definitiva Leitura"""
    try:
        # Recebe decisões de conflitos do frontend
        decisoes = request.json.get('decisoes', {}) if request.is_json else {}
        
        # Busca todos os rascunhos
        rascunhos = LeituraRascunho.query.all()
        
        if not rascunhos:
            return jsonify({
                'sucesso': False,
                'erro': 'Não há rascunhos para consolidar.'
            }), 400
        
        total_consolidado = 0
        total_substituido = 0
        total_pulado = 0
        
        # Processa cada rascunho
        for rascunho in rascunhos:
            rascunho_id_str = str(rascunho.id)
            
            # Verifica se existe leitura oficial do mesmo dia
            data_rascunho = rascunho.data_registro.date()
            leitura_existente = Leitura.query.filter(
                Leitura.quadro_id == rascunho.quadro_id,
                db.func.date(Leitura.data_registro) == data_rascunho
            ).first()
            
            if leitura_existente:
                # Há conflito - verifica decisão do usuário
                decisao = decisoes.get(rascunho_id_str, 'pular')
                
                if decisao == 'substituir':
                    # Remove a leitura antiga e adiciona a nova
                    db.session.delete(leitura_existente)
                    
                    leitura_definitiva = Leitura(
                        quadro_id=rascunho.quadro_id,
                        data_registro=rascunho.data_registro,
                        valor_leitura=rascunho.valor_leitura,
                        consumo_dia=rascunho.consumo_provisorio,
                        alerta_reset=rascunho.alerta_reset
                    )
                    db.session.add(leitura_definitiva)
                    db.session.delete(rascunho)
                    total_substituido += 1
                    
                elif decisao == 'manter_ambas':
                    # Mantém a antiga e adiciona a nova
                    leitura_definitiva = Leitura(
                        quadro_id=rascunho.quadro_id,
                        data_registro=rascunho.data_registro,
                        valor_leitura=rascunho.valor_leitura,
                        consumo_dia=rascunho.consumo_provisorio,
                        alerta_reset=rascunho.alerta_reset
                    )
                    db.session.add(leitura_definitiva)
                    db.session.delete(rascunho)
                    total_consolidado += 1
                    
                else:  # 'pular' ou sem decisão
                    # Não faz nada, mantém o rascunho
                    total_pulado += 1
            else:
                # Sem conflito - consolida normalmente
                leitura_definitiva = Leitura(
                    quadro_id=rascunho.quadro_id,
                    data_registro=rascunho.data_registro,
                    valor_leitura=rascunho.valor_leitura,
                    consumo_dia=rascunho.consumo_provisorio,
                    alerta_reset=rascunho.alerta_reset
                )
                db.session.add(leitura_definitiva)
                db.session.delete(rascunho)
                total_consolidado += 1
        
        db.session.commit()
        
        mensagem_partes = []
        if total_consolidado > 0:
            mensagem_partes.append(f'{total_consolidado} leitura(s) consolidada(s)')
        if total_substituido > 0:
            mensagem_partes.append(f'{total_substituido} substituída(s)')
        if total_pulado > 0:
            mensagem_partes.append(f'{total_pulado} pulada(s)')
        
        return jsonify({
            'sucesso': True,
            'mensagem': ', '.join(mensagem_partes) + '!',
            'total_consolidado': total_consolidado,
            'total_substituido': total_substituido,
            'total_pulado': total_pulado
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'sucesso': False,
            'erro': f'Erro ao consolidar: {str(e)}'
        }), 500


@app.route('/quadros')
def listar_quadros():
    """Lista todos os quadros"""
    quadros = Quadro.query.filter_by(ativo=True).all()
    return jsonify([q.to_dict() for q in quadros])


@app.route('/quadro/<int:quadro_id>/ultima-leitura')
def ultima_leitura_quadro(quadro_id):
    """Retorna a última leitura de um quadro específico"""
    quadro = Quadro.query.get(quadro_id)
    
    if not quadro:
        return jsonify({
            'erro': 'Quadro não encontrado'
        }), 404
    
    ultima_leitura = Leitura.query.filter_by(quadro_id=quadro_id)\
        .order_by(Leitura.data_registro.desc()).first()
    
    if ultima_leitura:
        return jsonify({
            'existe': True,
            'valor': ultima_leitura.valor_leitura,
            'data': ultima_leitura.data_registro.strftime('%d/%m/%Y às %H:%M'),
            'consumo_anterior': ultima_leitura.consumo_dia,
            'alerta_reset': ultima_leitura.alerta_reset
        })
    else:
        return jsonify({
            'existe': False,
            'mensagem': 'Nenhuma leitura registrada ainda para este quadro'
        })


@app.route('/leituras')
def listar_leituras():
    """Lista todas as leituras"""
    leituras = Leitura.query.order_by(Leitura.data_registro.desc()).limit(50).all()
    return jsonify([l.to_dict() for l in leituras])


# ========================================
# ROTAS ADMINISTRATIVAS
# ========================================

@app.route('/admin/quadros')
def admin_quadros():
    """Interface administrativa para gerenciar quadros"""
    quadros = Quadro.query.order_by(Quadro.nome).all()
    
    # Variáveis para a sidebar
    ip_local = obter_ip_local()
    url_mobile = f"http://{ip_local}:5000/registrar"
    qrcode_img = gerar_qrcode(url_mobile)
    total_rascunhos = LeituraRascunho.query.count()
    
    return render_template('admin_quadros.html', 
                         quadros=quadros,
                         qrcode_img=qrcode_img,
                         ip_local=ip_local,
                         total_rascunhos=total_rascunhos)


@app.route('/admin/quadros/criar', methods=['POST'])
def criar_quadro():
    """Cria um novo quadro"""
    try:
        nome = request.form.get('nome', '').strip()
        localizacao = request.form.get('localizacao', '').strip()
        
        if not nome or not localizacao:
            return jsonify({
                'sucesso': False,
                'erro': 'Nome e localização são obrigatórios.'
            }), 400
        
        # Verifica se já existe um quadro com esse nome
        quadro_existente = Quadro.query.filter_by(nome=nome).first()
        if quadro_existente:
            return jsonify({
                'sucesso': False,
                'erro': 'Já existe um quadro com este nome.'
            }), 400
        
        novo_quadro = Quadro(
            nome=nome,
            localizacao=localizacao,
            ativo=True
        )
        
        db.session.add(novo_quadro)
        db.session.commit()
        
        return jsonify({
            'sucesso': True,
            'mensagem': f'Quadro "{nome}" criado com sucesso!',
            'quadro': novo_quadro.to_dict()
        }), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'sucesso': False,
            'erro': f'Erro ao criar quadro: {str(e)}'
        }), 500


@app.route('/admin/quadros/editar/<int:id>', methods=['POST'])
def editar_quadro(id):
    """Edita um quadro existente"""
    try:
        quadro = Quadro.query.get(id)
        
        if not quadro:
            return jsonify({
                'sucesso': False,
                'erro': 'Quadro não encontrado.'
            }), 404
        
        nome = request.form.get('nome', '').strip()
        localizacao = request.form.get('localizacao', '').strip()
        ativo = request.form.get('ativo') == 'true'
        
        if not nome or not localizacao:
            return jsonify({
                'sucesso': False,
                'erro': 'Nome e localização são obrigatórios.'
            }), 400
        
        # Verifica se já existe outro quadro com esse nome
        quadro_existente = Quadro.query.filter(
            Quadro.nome == nome,
            Quadro.id != id
        ).first()
        
        if quadro_existente:
            return jsonify({
                'sucesso': False,
                'erro': 'Já existe outro quadro com este nome.'
            }), 400
        
        quadro.nome = nome
        quadro.localizacao = localizacao
        quadro.ativo = ativo
        
        db.session.commit()
        
        return jsonify({
            'sucesso': True,
            'mensagem': f'Quadro "{nome}" atualizado com sucesso!',
            'quadro': quadro.to_dict()
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'sucesso': False,
            'erro': f'Erro ao editar quadro: {str(e)}'
        }), 500


@app.route('/admin/quadros/excluir/<int:id>', methods=['POST'])
def excluir_quadro(id):
    """Exclui ou desativa um quadro (soft delete se houver leituras)"""
    try:
        quadro = Quadro.query.get(id)
        
        if not quadro:
            return jsonify({
                'sucesso': False,
                'erro': 'Quadro não encontrado.'
            }), 404
        
        # Verifica se existem leituras associadas
        tem_leituras = Leitura.query.filter_by(quadro_id=id).count() > 0
        
        if tem_leituras:
            # Soft Delete - apenas desativa o quadro
            quadro.ativo = False
            db.session.commit()
            
            return jsonify({
                'sucesso': True,
                'tipo': 'desativado',
                'mensagem': f'Quadro "{quadro.nome}" foi DESATIVADO (possui leituras associadas).'
            }), 200
        else:
            # Delete real - remove do banco
            nome_quadro = quadro.nome
            db.session.delete(quadro)
            db.session.commit()
            
            return jsonify({
                'sucesso': True,
                'tipo': 'excluido',
                'mensagem': f'Quadro "{nome_quadro}" foi EXCLUÍDO permanentemente.'
            }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'sucesso': False,
            'erro': f'Erro ao excluir quadro: {str(e)}'
        }), 500


# ========================================
# ROTAS DE ANÁLISE E RELATÓRIOS
# ========================================

@app.route('/analise')
def analise():
    """Página de análise e inteligência de dados"""
    quadros = Quadro.query.filter_by(ativo=True).order_by(Quadro.nome).all()
    
    # Variáveis para a sidebar
    ip_local = obter_ip_local()
    url_mobile = f"http://{ip_local}:5000/registrar"
    qrcode_img = gerar_qrcode(url_mobile)
    total_rascunhos = LeituraRascunho.query.count()
    
    return render_template('analise.html', 
                         quadros=quadros,
                         qrcode_img=qrcode_img,
                         ip_local=ip_local,
                         total_rascunhos=total_rascunhos)


@app.route('/api/analise/dados', methods=['GET'])
def api_analise_dados():
    """Retorna dados de leituras filtrados para análise"""
    try:
        # Recebe parâmetros do filtro
        data_inicio = request.args.get('data_inicio')
        data_fim = request.args.get('data_fim')
        quadro_id = request.args.get('quadro_id', type=int)
        
        # Monta a query base
        query = Leitura.query
        
        # Aplica filtros
        if data_inicio:
            data_inicio_dt = datetime.strptime(data_inicio, '%Y-%m-%d')
            query = query.filter(Leitura.data_registro >= data_inicio_dt)
        
        if data_fim:
            data_fim_dt = datetime.strptime(data_fim, '%Y-%m-%d')
            # Adiciona 23:59:59 para incluir todo o dia
            data_fim_dt = datetime.combine(data_fim_dt.date(), datetime.max.time())
            query = query.filter(Leitura.data_registro <= data_fim_dt)
        
        if quadro_id:
            query = query.filter(Leitura.quadro_id == quadro_id)
        
        # Ordena por data
        leituras = query.order_by(Leitura.data_registro.asc()).all()
        
        # Prepara dados para a tabela
        tabela_dados = []
        for leitura in leituras:
            tabela_dados.append({
                'id': leitura.id,
                'quadro_id': leitura.quadro_id,
                'quadro_nome': leitura.quadro.nome,
                'quadro_localizacao': leitura.quadro.localizacao,
                'data_registro': leitura.data_registro.strftime('%d/%m/%Y'),
                'hora_registro': leitura.data_registro.strftime('%H:%M:%S'),
                'valor_leitura': round(leitura.valor_leitura, 2),
                'consumo_dia': round(leitura.consumo_dia, 2) if leitura.consumo_dia else 0,
                'alerta_reset': leitura.alerta_reset
            })
        
        # Prepara dados para o gráfico
        # Organiza por data e quadro
        dados_grafico = {}
        quadros_dict = {}
        
        for leitura in leituras:
            data_str = leitura.data_registro.strftime('%Y-%m-%d')
            quadro_nome = leitura.quadro.nome
            
            if data_str not in dados_grafico:
                dados_grafico[data_str] = {}
            
            if quadro_nome not in dados_grafico[data_str]:
                dados_grafico[data_str][quadro_nome] = 0
            
            # Soma o consumo do dia
            if leitura.consumo_dia:
                dados_grafico[data_str][quadro_nome] += leitura.consumo_dia
            
            # Guarda informações do quadro
            if quadro_nome not in quadros_dict:
                quadros_dict[quadro_nome] = {
                    'id': leitura.quadro_id,
                    'nome': quadro_nome
                }
        
        # Formata dados para Chart.js
        datas_ordenadas = sorted(dados_grafico.keys())
        
        # Dados separados por quadro
        datasets_separados = []
        cores = [
            '#667eea', '#764ba2', '#f093fb', '#4facfe',
            '#43e97b', '#fa709a', '#fee140', '#30cfd0',
            '#a8edea', '#fed6e3', '#c471f5', '#12c2e9'
        ]
        
        for idx, (quadro_nome, quadro_info) in enumerate(quadros_dict.items()):
            dados_quadro = []
            for data in datas_ordenadas:
                valor = dados_grafico[data].get(quadro_nome, 0)
                dados_quadro.append(round(valor, 2))
            
            datasets_separados.append({
                'label': quadro_nome,
                'data': dados_quadro,
                'borderColor': cores[idx % len(cores)],
                'backgroundColor': cores[idx % len(cores)] + '20',
                'tension': 0.4,
                'fill': False
            })
        
        # Dados agrupados (soma total por dia)
        dados_agrupados = []
        for data in datas_ordenadas:
            total_dia = sum(dados_grafico[data].values())
            dados_agrupados.append(round(total_dia, 2))
        
        dataset_agrupado = [{
            'label': 'Consumo Total da Empresa',
            'data': dados_agrupados,
            'borderColor': '#667eea',
            'backgroundColor': 'rgba(102, 126, 234, 0.1)',
            'tension': 0.4,
            'fill': True,
            'borderWidth': 3
        }]
        
        # Formata labels das datas
        labels = [datetime.strptime(d, '%Y-%m-%d').strftime('%d/%m/%Y') for d in datas_ordenadas]
        
        return jsonify({
            'sucesso': True,
            'tabela': tabela_dados,
            'grafico': {
                'labels': labels,
                'datasets_separados': datasets_separados,
                'dataset_agrupado': dataset_agrupado
            },
            'total_registros': len(tabela_dados)
        }), 200
        
    except Exception as e:
        return jsonify({
            'sucesso': False, 
            'erro': str(e)
        }), 500

# ROTAS DE IMPORTAÇÃO
# ========================================

@app.route('/admin/importacao')
def importacao():
    """Página de importação de dados históricos"""
    # Variáveis para a sidebar
    ip_local = obter_ip_local()
    url_mobile = f"http://{ip_local}:5000/registrar"
    qrcode_img = gerar_qrcode(url_mobile)
    total_rascunhos = LeituraRascunho.query.count()
    
    return render_template('importar.html',
                         qrcode_img=qrcode_img,
                         ip_local=ip_local,
                         total_rascunhos=total_rascunhos)


@app.route('/admin/importacao/modelo')
def download_modelo():
    """Gera e retorna modelo de planilha Excel para importação"""
    # Cria um DataFrame de exemplo
    df = pd.DataFrame({
        'Data': ['01/01/2024', '02/01/2024', '03/01/2024'],
        'Quadro': ['Galpão A', 'Galpão A', 'Escritório'],
        'Localizacao': ['Área de Produção', 'Área de Produção', 'Prédio Administrativo'],
        'Leitura': [1000.50, 1025.75, 500.00]
    })
    
    # Cria buffer em memória
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Leituras')
        
        # Adiciona instruções em outra aba
        instrucoes = pd.DataFrame({
            'Instruções para Importação': [
                '1. A coluna "Data" deve estar no formato DD/MM/AAAA ou DD/MM/AAAA HH:MM:SS',
                '2. A coluna "Quadro" é o nome do quadro (será criado automaticamente se não existir)',
                '3. A coluna "Localizacao" é a localização do quadro (obrigatória para novos quadros)',
                '4. A coluna "Leitura" é o valor da leitura do medidor em kWh',
                '5. O sistema calculará automaticamente o consumo com base na diferença entre leituras',
                '6. Registros duplicados (mesmo quadro e mesma data) serão ignorados',
                '7. Se um valor de leitura for menor que o anterior, será marcado como "Reset"',
                '8. Mantenha os dados ordenados por data para melhor precisão'
            ]
        })
        instrucoes.to_excel(writer, index=False, sheet_name='Instruções')
    
    output.seek(0)
    
    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name='modelo_importacao_leituras.xlsx'
    )


@app.route('/admin/importacao/processar', methods=['POST'])
def processar_importacao():
    """Processa arquivo Excel de importação de dados históricos"""
    try:
        # Verifica se arquivo foi enviado
        if 'arquivo' not in request.files:
            return jsonify({
                'sucesso': False,
                'erro': 'Nenhum arquivo foi enviado.'
            }), 400
        
        arquivo = request.files['arquivo']
        
        if arquivo.filename == '':
            return jsonify({
                'sucesso': False,
                'erro': 'Nenhum arquivo selecionado.'
            }), 400
        
        if not arquivo.filename.endswith(('.xlsx', '.xls')):
            return jsonify({
                'sucesso': False,
                'erro': 'Formato inválido. Use arquivos .xlsx ou .xls'
            }), 400
        
        # Salva arquivo temporariamente
        filename = secure_filename(arquivo.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        arquivo.save(filepath)
        
        # Lê o arquivo Excel
        try:
            df = pd.read_excel(filepath, sheet_name=0)
        except Exception as e:
            os.remove(filepath)
            return jsonify({
                'sucesso': False,
                'erro': f'Erro ao ler arquivo Excel: {str(e)}'
            }), 400
        
        # Valida colunas obrigatórias
        colunas_obrigatorias = ['Data', 'Quadro', 'Localizacao', 'Leitura']
        colunas_faltantes = [col for col in colunas_obrigatorias if col not in df.columns]
        
        if colunas_faltantes:
            os.remove(filepath)
            return jsonify({
                'sucesso': False,
                'erro': f'Colunas obrigatórias faltando: {", ".join(colunas_faltantes)}'
            }), 400
        
        # Processa importação
        resultado = processar_dados_importacao(df)
        
        # Remove arquivo temporário
        os.remove(filepath)
        
        if resultado['sucesso']:
            return jsonify(resultado), 200
        else:
            return jsonify(resultado), 400
        
    except Exception as e:
        return jsonify({
            'sucesso': False,
            'erro': f'Erro ao processar importação: {str(e)}'
        }), 500


def processar_dados_importacao(df):
    """Processa o DataFrame e importa os dados para o banco"""
    registros_inseridos = 0
    registros_duplicados = 0
    quadros_criados = []
    erros = []
    
    try:
        # Remove linhas com dados vazios
        df = df.dropna(subset=['Data', 'Quadro', 'Leitura'])
        
        # Agrupa por quadro para processar separadamente
        quadros_processados = {}
        
        for index, row in df.iterrows():
            try:
                # Converte data
                if isinstance(row['Data'], str):
                    # Tenta vários formatos de data
                    for fmt in ['%d/%m/%Y', '%d/%m/%Y %H:%M:%S', '%Y-%m-%d', '%Y-%m-%d %H:%M:%S']:
                        try:
                            data_leitura = datetime.strptime(row['Data'], fmt)
                            break
                        except ValueError:
                            continue
                    else:
                        raise ValueError(f"Formato de data inválido: {row['Data']}")
                else:
                    data_leitura = pd.to_datetime(row['Data'])
                
                nome_quadro = str(row['Quadro']).strip()
                localizacao = str(row['Localizacao']).strip()
                valor_leitura = float(row['Leitura'])
                
                # Busca ou cria o quadro
                quadro = Quadro.query.filter_by(nome=nome_quadro).first()
                
                if not quadro:
                    quadro = Quadro(
                        nome=nome_quadro,
                        localizacao=localizacao,
                        ativo=True
                    )
                    db.session.add(quadro)
                    db.session.flush()  # Obtém o ID sem commitar
                    quadros_criados.append(nome_quadro)
                
                # Verifica duplicata (mesma data e quadro)
                data_inicio = data_leitura.replace(hour=0, minute=0, second=0)
                data_fim = data_leitura.replace(hour=23, minute=59, second=59)
                
                existe = Leitura.query.filter(
                    Leitura.quadro_id == quadro.id,
                    Leitura.data_registro >= data_inicio,
                    Leitura.data_registro <= data_fim
                ).first()
                
                if existe:
                    registros_duplicados += 1
                    continue
                
                # Cria leitura temporária (consumo será calculado depois)
                nova_leitura = Leitura(
                    quadro_id=quadro.id,
                    data_registro=data_leitura,
                    valor_leitura=valor_leitura,
                    consumo_dia=0,  # Será recalculado
                    alerta_reset=False
                )
                
                db.session.add(nova_leitura)
                registros_inseridos += 1
                
                # Marca quadro para recálculo
                quadros_processados[quadro.id] = True
                
            except Exception as e:
                erros.append(f"Linha {index + 2}: {str(e)}")
        
        # Comita as inserções
        db.session.commit()
        
        # Recalcula consumo para cada quadro processado
        for quadro_id in quadros_processados.keys():
            recalcular_consumo_quadro(quadro_id)
        
        return {
            'sucesso': True,
            'mensagem': 'Importação concluída com sucesso!',
            'detalhes': {
                'registros_inseridos': registros_inseridos,
                'registros_duplicados': registros_duplicados,
                'quadros_criados': quadros_criados,
                'erros': erros
            }
        }
        
    except Exception as e:
        db.session.rollback()
        return {
            'sucesso': False,
            'erro': f'Erro durante importação: {str(e)}'
        }


def recalcular_consumo_quadro(quadro_id):
    """Recalcula o consumo para todas as leituras de um quadro"""
    # Busca todas as leituras do quadro ordenadas por data
    leituras = Leitura.query.filter_by(quadro_id=quadro_id)\
        .order_by(Leitura.data_registro.asc()).all()
    
    leitura_anterior = None
    
    for leitura in leituras:
        if leitura_anterior is None:
            # Primeira leitura: consumo = 0
            leitura.consumo_dia = 0
            leitura.alerta_reset = False
        else:
            if leitura.valor_leitura >= leitura_anterior.valor_leitura:
                # Consumo normal
                leitura.consumo_dia = leitura.valor_leitura - leitura_anterior.valor_leitura
                leitura.alerta_reset = False
            else:
                # Reset detectado (medidor virou)
                leitura.consumo_dia = leitura.valor_leitura
                leitura.alerta_reset = True
        
        leitura_anterior = leitura


# ========================================
# API: CONTROLE DE SESSÃO DE LEITURA
# ========================================

@app.route('/api/sessao/iniciar', methods=['POST'])
def api_sessao_iniciar():
    """Inicia uma nova sessão de leitura"""
    try:
        # Verifica se já existe uma sessão ativa
        sessao_ativa = SessaoLeitura.query.filter_by(ativa=True).first()
        if sessao_ativa:
            return jsonify({
                'sucesso': False,
                'mensagem': 'Já existe uma sessão ativa'
            }), 400
        
        # Cria nova sessão
        nova_sessao = SessaoLeitura(ativa=True, iniciada_por='Supervisor')
        db.session.add(nova_sessao)
        db.session.commit()
        
        return jsonify({
            'sucesso': True,
            'mensagem': 'Sessão iniciada com sucesso',
            'sessao': nova_sessao.to_dict()
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'sucesso': False,
            'mensagem': f'Erro ao iniciar sessão: {str(e)}'
        }), 500


@app.route('/api/sessao/encerrar', methods=['POST'])
def api_sessao_encerrar():
    """Encerra a sessão ativa e deleta todos os rascunhos (Opção A)"""
    try:
        # Busca sessão ativa
        sessao_ativa = SessaoLeitura.query.filter_by(ativa=True).first()
        if not sessao_ativa:
            return jsonify({
                'sucesso': False,
                'mensagem': 'Não há sessão ativa'
            }), 400
        
        # Encerra sessão
        sessao_ativa.ativa = False
        sessao_ativa.data_fim = datetime.now()
        
        # OPÇÃO A: Deleta todos os rascunhos
        rascunhos_deletados = LeituraRascunho.query.delete()
        
        db.session.commit()
        
        return jsonify({
            'sucesso': True,
            'mensagem': f'Sessão encerrada e {rascunhos_deletados} rascunhos deletados',
            'rascunhos_deletados': rascunhos_deletados
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'sucesso': False,
            'mensagem': f'Erro ao encerrar sessão: {str(e)}'
        }), 500


@app.route('/api/sessao/status', methods=['GET'])
def api_sessao_status():
    """Retorna o status da sessão atual"""
    try:
        sessao_ativa = SessaoLeitura.query.filter_by(ativa=True).first()
        
        if sessao_ativa:
            return jsonify({
                'ativa': True,
                'sessao': sessao_ativa.to_dict()
            })
        else:
            return jsonify({
                'ativa': False,
                'sessao': None
            })
            
    except Exception as e:
        return jsonify({
            'ativa': False,
            'mensagem': f'Erro ao verificar status: {str(e)}'
        }), 500


@app.route('/api/rascunhos/mobile', methods=['GET'])
def api_rascunhos_mobile():
    """Retorna lista de quadros com status e valores para interface mobile"""
    try:
        # Busca todos os quadros ativos ordenados alfabeticamente
        quadros = Quadro.query.filter_by(ativo=True).order_by(Quadro.nome).all()
        
        # Busca todos os rascunhos do dia atual
        hoje = datetime.now().date()
        rascunhos_hoje = LeituraRascunho.query.filter(
            db.func.date(LeituraRascunho.data_registro) == hoje
        ).all()
        
        # Cria dicionário de rascunhos por quadro_id
        rascunhos_dict = {r.quadro_id: r for r in rascunhos_hoje}
        
        # Monta lista de resposta
        resultado = []
        for quadro in quadros:
            rascunho = rascunhos_dict.get(quadro.id)
            resultado.append({
                'quadro_id': quadro.id,
                'quadro_nome': quadro.nome,
                'quadro_localizacao': quadro.localizacao,
                'cadastrado': rascunho is not None,
                'valor_leitura': rascunho.valor_leitura if rascunho else None,
                'alerta_reset': rascunho.alerta_reset if rascunho else False,
                'rascunho_id': rascunho.id if rascunho else None
            })
        
        return jsonify({
            'sucesso': True,
            'quadros': resultado
        })
        
    except Exception as e:
        return jsonify({
            'sucesso': False,
            'mensagem': f'Erro ao buscar quadros: {str(e)}'
        }), 500


@app.route('/api/rascunhos/revisao', methods=['GET'])
def api_rascunhos_revisao():
    """Retorna dados de revisão em JSON para atualização em tempo real"""
    try:
        rascunhos = LeituraRascunho.query.all()
        dados_revisao = []
        
        for rascunho in rascunhos:
            # Calcula média dos últimos 90 dias
            noventa_dias_atras = datetime.now() - timedelta(days=90)
            media_90_dias = db.session.query(func.avg(Leitura.consumo_dia))\
                .filter(Leitura.quadro_id == rascunho.quadro_id)\
                .filter(Leitura.data_registro >= noventa_dias_atras)\
                .filter(Leitura.consumo_dia.isnot(None))\
                .scalar()
            
            media_90_dias = media_90_dias if media_90_dias else 0
            
            # Busca o último valor registrado oficialmente
            ultima_leitura_oficial = Leitura.query.filter_by(quadro_id=rascunho.quadro_id)\
                .order_by(Leitura.data_registro.desc()).first()
            
            ultimo_valor_oficial = ultima_leitura_oficial.valor_leitura if ultima_leitura_oficial else 0
            ultima_data_oficial = ultima_leitura_oficial.data_registro.strftime('%d/%m/%Y %H:%M') if ultima_leitura_oficial else 'Nunca'
            
            # Calcula desvio percentual
            desvio_percentual = 0
            status_desvio = 'normal'
            
            if media_90_dias > 0 and rascunho.consumo_provisorio:
                desvio_percentual = ((rascunho.consumo_provisorio - media_90_dias) / media_90_dias) * 100
                
                if abs(desvio_percentual) > 50:
                    status_desvio = 'critico'
                elif abs(desvio_percentual) > 30:
                    status_desvio = 'alerta'
            
            dados_revisao.append({
                'id': rascunho.id,
                'quadro_id': rascunho.quadro_id,
                'quadro_nome': rascunho.quadro.nome,
                'quadro_localizacao': rascunho.quadro.localizacao,
                'valor_leitura': rascunho.valor_leitura,
                'consumo_provisorio': rascunho.consumo_provisorio,
                'alerta_reset': rascunho.alerta_reset,
                'media_90_dias': round(media_90_dias, 2),
                'desvio_percentual': round(desvio_percentual, 1),
                'status_desvio': status_desvio,
                'ultimo_valor_oficial': round(ultimo_valor_oficial, 2),
                'ultima_data_oficial': ultima_data_oficial
            })
        
        return jsonify({
            'sucesso': True,
            'rascunhos': dados_revisao,
            'total': len(dados_revisao)
        })
        
    except Exception as e:
        return jsonify({
            'sucesso': False,
            'mensagem': f'Erro ao buscar rascunhos: {str(e)}'
        }), 500

    
    db.session.commit()




# ========================================
# EXECUÇÃO
# ========================================

def abrir_navegador():
    """Abre o navegador automaticamente após 1.5 segundos"""
    import time
    time.sleep(1.5)
    webbrowser.open('http://localhost:5000')

if __name__ == '__main__':
    # Verifica se o banco existe, se não, cria e popula
    if not os.path.exists('energia.db'):
        print("📦 Banco de dados não encontrado. Criando...")
        inicializar_banco()
    else:
        print("✅ Banco de dados já existe!")
    
    # Inicia o servidor Flask
    print("\n🚀 Iniciando servidor Flask...")
    print("🌐 Acesse: http://localhost:5000")
    print("📱 Na rede local: http://<IP-DO-PC>:5000")
    
    # Abre o navegador apenas no processo principal (não no reloader do debug)
    if os.environ.get('WERKZEUG_RUN_MAIN') != 'true':
        threading.Thread(target=abrir_navegador, daemon=True).start()
    
    app.run(debug=True, host='0.0.0.0', port=5000)
