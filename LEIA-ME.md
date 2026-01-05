# ====================================================
# SISTEMA DE MONITORAMENTO DE ENERGIA - GUIA DE USO
# ====================================================

## 📋 Instalação

### Passo 1: Instalar Python (se necessário)
- Baixe e instale Python 3.8+ em: https://www.python.org/downloads/
- Durante a instalação, marque "Add Python to PATH"

### Passo 2: Instalar Dependências
- Execute com duplo clique: **INSTALAR_REQUISITOS.bat**
- Aguarde a instalação dos pacotes necessários

## 🚀 Como Usar

### Iniciar o Sistema
1. Execute com duplo clique: **INICIAR_SISTEMA.bat**
2. Aguarde o servidor iniciar
3. Acesse no navegador: http://localhost:5000

### Acesso Mobile (Funcionários)
1. Abra o dashboard no PC (http://localhost:5000)
2. Escaneie o QR Code exibido na lateral direita
3. O celular abrirá automaticamente a página de registro
4. Selecione o quadro e insira a leitura

## 📱 Funcionalidades

### Dashboard Principal (/)
- Visualização de consumo total do dia
- Média de consumo dos últimos 3 meses
- Tabela com status de todos os quadros
- QR Code para acesso mobile rápido

### Registro de Leitura (/registrar)
- Seleção do quadro de energia
- Exibição automática da última leitura
- Validação de inconsistências (valores menores)
- Sistema de confirmação para medidores que "viraram"

## 🔧 Estrutura do Projeto

```
Contagem de Quadros/
│
├── app.py                      # Aplicação principal Flask
├── energia.db                  # Banco de dados SQLite (criado automaticamente)
├── requirements.txt            # Dependências Python
│
├── templates/
│   ├── dashboard.html          # Dashboard principal
│   └── mobile_form.html        # Formulário de registro mobile
│
├── INSTALAR_REQUISITOS.bat     # Instalador de dependências
├── INICIAR_SISTEMA.bat         # Inicializador do sistema
└── LEIA-ME.md                  # Este arquivo

```

## 🌐 Acesso na Rede Local

O sistema roda na rede Wi-Fi local. Para acessar de outros dispositivos:

1. No PC servidor, abra o dashboard
2. Veja o IP exibido (ex: 192.168.1.10)
3. Em outros dispositivos na mesma rede, acesse: http://IP:5000

## ⚠️ Detecção de Inconsistências

Quando um valor registrado é **menor** que o anterior:
- O sistema detecta automaticamente
- Abre um modal perguntando se o medidor "virou" (zerou)
- Se confirmado, registra com alerta de RESET
- O consumo é calculado considerando a virada do medidor

## 🗄️ Banco de Dados

- **Quadros:** Contém os medidores cadastrados
  - Galpão A (Área de Produção)
  - Escritório (Prédio Administrativo)
  - Recepção (Entrada Principal)

- **Leituras:** Histórico completo de todas as medições
  - Valor da leitura
  - Consumo calculado
  - Data e hora do registro
  - Alertas de reset

## 🛠️ Solução de Problemas

### Erro: Python não encontrado
- Instale Python 3.8+ e marque "Add to PATH"

### Erro: Falha ao instalar requisitos
- Abra CMD como Administrador
- Execute: `python -m pip install --upgrade pip`
- Execute novamente: INSTALAR_REQUISITOS.bat

### Porta 5000 em uso
- Feche outros programas que usam a porta 5000
- Ou edite app.py e mude `port=5000` para outro número

## 💡 Dicas

- O dashboard atualiza automaticamente a cada 30 segundos
- Funcionários podem adicionar o site aos favoritos do celular
- Cada quadro pode ter múltiplas leituras por dia
- Histórico completo fica salvo no banco de dados

## 📞 Suporte

Para problemas ou dúvidas, verifique:
1. Python está instalado corretamente
2. Dependências foram instaladas
3. Firewall não está bloqueando a porta 5000
4. PC e celulares estão na mesma rede Wi-Fi
