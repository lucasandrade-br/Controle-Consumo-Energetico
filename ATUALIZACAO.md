# 📅 Atualização: Registro de Leituras de Dias Anteriores

## O que mudou?

Agora o sistema permite registrar leituras de dias anteriores, não apenas do dia atual! Se você esqueceu de cadastrar as leituras de ontem ou de qualquer dia passado, pode fazer isso facilmente.

## Como funciona?

### 1️⃣ **Iniciar Sessão com Data Personalizada**
- Ao clicar em "Iniciar Sessão" na tela de Revisão, aparecerá um modal
- Selecione a data das leituras que deseja registrar
- Por padrão, vem a data de hoje, mas você pode alterar para qualquer dia anterior
- Clique em "Iniciar Sessão"

### 2️⃣ **Registrar Leituras**
- Os operadores podem registrar as leituras normalmente pelo celular
- As leituras serão salvas com a data selecionada no início da sessão
- A data de referência aparece na interface mobile

### 3️⃣ **Consolidar Dados**
- Quando finalizar, as leituras serão consolidadas com a data correta

## 🔧 Instalação/Atualização

### Para quem já tem o sistema rodando:

**Não é necessário fazer nada!** 🎉

1. **Reinicie o sistema** normalmente:
   ```bash
   INICIAR_SISTEMA.bat
   ```

O próprio sistema detectará automaticamente que o banco precisa ser atualizado e aplicará a migração na primeira execução.

### Para instalação nova:

Nenhuma ação adicional necessária! O banco já será criado com a estrutura atualizada.

## 📝 Detalhes Técnicos

### Mudanças no Banco de Dados:
- Adicionada coluna `data_referencia` (tipo DATE) na tabela `sessoes_leitura`
- Armazena a data que está sendo registrada (pode ser hoje ou dia anterior)

### Mudanças na API:
- `POST /api/sessao/iniciar` - Agora aceita parâmetro `data_referencia` (formato: YYYY-MM-DD)
- `GET /api/sessao/status` - Retorna `data_referencia` quando há sessão ativa

### Mudanças nas Interfaces:
- **Tela de Revisão**: Modal para selecionar data ao iniciar sessão
- **Interface Mobile**: Exibe a data de referência quando sessão está ativa
- Ambas mostram a data sendo registrada no badge de status

## ⚠️ Observações Importantes

1. **Limpeza de Rascunhos**: Ao iniciar uma nova sessão, todos os rascunhos pendentes são deletados (comportamento existente)

2. **Validação de Conflitos**: Se já existe uma leitura oficial para o mesmo quadro no mesmo dia, o sistema detectará o conflito durante a consolidação

3. **Cálculo de Consumo**: O consumo é calculado com base na última leitura OFICIAL do quadro, independente da data

## 🎯 Casos de Uso

### Exemplo 1: Esqueceu de registrar ontem
```
1. Segunda-feira, 08h: Percebe que esqueceu de registrar sexta-feira
2. Abre o sistema e clica em "Iniciar Sessão"
3. Seleciona a data de sexta-feira (05/01/2026)
4. Registra todas as leituras de sexta
5. Consolida - as leituras ficam salvas com data de sexta
```

### Exemplo 2: Fim de semana/feriado
```
1. Segunda após feriado
2. Precisa registrar quinta e sexta
3. Inicia sessão para quinta → registra → consolida
4. Inicia nova sessão para sexta → registra → consolida
```

## 🐛 Resolução de Problemas

**Erro: "Coluna data_referencia não existe"**
- Reinicie o sistema - a migração será aplicada automaticamente

**Data não aparece na interface mobile**
- Verifique se a sessão está realmente ativa
- Recarregue a página (botão de refresh)

**Leituras consolidadas com data errada**
- Verifique a data selecionada ao iniciar a sessão
- A data fica visível no badge "AO VIVO - DD/MM/YYYY"

## 📞 Suporte

Se tiver dúvidas ou problemas, verifique:
1. Se reiniciou o sistema após atualizar (a migração é automática)
2. Se o banco de dados não está corrompido
3. Os logs no terminal ao iniciar o sistema
