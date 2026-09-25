# TermoGuará — duas câmaras, seis sensores e dois PIDs

Versão reescrita a partir de `sketch_aug31a.ino` e `Aplicativo05.py`. Os originais em E: foram apenas lidos e permanecem intactos. Destino: **Nano clássico ATmega328P, 5 V**. Outros Nano exigem revisão de pinagem, níveis lógicos e bibliotecas.

## O que precisa ser resolvido antes de aquecer

1. **RREF marcado 431 = 430 Ω**: módulo destinado a PT100. O PT1000 tem aproximadamente 1000 Ω a 0 °C; sua resistência excede essa referência. Não basta escrever `4300` no programa: use dois módulos próprios para PT1000 com RREF 4,3 kΩ, ou substitua cada referência por resistor adequado de precisão e baixo coeficiente térmico, verificando o esquema do módulo. Depois registre os valores reais em `Config.h`.
2. NTC informado: **100 kΩ a 25 °C, Beta 3950 K**, provisório. A indicação comercial não comprova tolerância nem intervalo do Beta. Confira modelo, faixa térmica e calibre os quatro sensores.
3. Os **dois resistores de 330 Ω** serão usados nos gates; os **dois de 10 kΩ**, como pull-down de gate. Faltam **quatro resistores de 10 kΩ de precisão (preferencialmente 0,1%, baixo coeficiente térmico)** para os divisores NTC. Não reutilize os pull-downs como resistores de medição.
4. O usuário informou máximo de trabalho de 90 °C. Esta versão corta quando qualquer sensor da câmara atinge **90 °C**, limita o alvo a **85 °C** e a saída a **128/255 (~50%)** para comissionamento. Esses valores não garantem que a inércia térmica impeça ultrapassar 90 °C. Avalie um corte inferior e proteção física compatível com os componentes.
5. `HARDWARE_VERIFIED=false` mantém a aquisição disponível e rejeita START. Só altere após corrigir RREF, conferir parâmetros, calibração, sensores, montagem e testar os desligamentos. Há também uma verificação de compilação que impede liberar PT1000 com RREF de 430 Ω.

## Análise dos códigos recebidos

| Encontrado | Consequência | Implementação nova |
|---|---|---|
| MAX31856 / termopar K | Incompatível com os MAX31865/PT1000 descritos | MAX31865 em dois fios, nominal 1000 Ω |
| ON liga dois MOSFETs em nível alto | Potência contínua, sem regulação | Dois PIDs no Nano com PWM separado |
| Ausência de leitura NTC/ADS | Sem temperatura da fonte quente | Quatro divisores, dois ADS1115 |
| Sem corte por sensor, temperatura, tempo ou perda serial | Aquecimento pode persistir após falha do PC | Intertravamentos locais e falhas retidas |
| Fechamento do app sem OFF | Aquecimento pode continuar | STOP no fechamento e timeout de heartbeat |
| Primeira porta serial selecionada automaticamente | Pode comunicar com outro dispositivo | Porta escolhida pelo operador e identificação do firmware |
| Regex extrai números de qualquer linha; buffer descartado | Pode confundir mensagens com medidas e perder dados | Protocolo tipado, versão, tamanho e valores validados |
| Correções antigas a1/b1 e a2/b2 | Calibração não transferível aos novos sensores | Correção dos seis sensores no firmware, inicialmente identidade |
| CSV só ao término e dados em memória | Risco de perder ensaio interrompido | CSV incremental, flush a cada quadro, metadados e eventos |
| Thread lê/modifica estado usado pela GUI | Concorrência desnecessária | Serial não bloqueante pelo loop Tk, sem thread de interface |

O novo aplicativo usa Tkinter/ttk e Matplotlib. Mantém curvas ao vivo, cronômetro por câmara e registro; calibração passa para o firmware para afetar também o controle e os limites. **WhatsApp, ícones personalizados e ajustes de tendência do aplicativo antigo não foram portados.** Não são necessários para aquisição/controle; ajuste de modelos deve ser feito sobre os dados salvos, sem substituir as medidas originais por curvas ajustadas. Não foram utilizados os antigos coeficientes de calibração.

## Arquivos e instalação

- `firmware/TermoGuara/TermoGuara.ino`: programa para o Nano.
- `firmware/TermoGuara/Config.h`: parâmetros físicos, calibração e limites.
- `Aplicativo06.py`: interface; `protocol.py`: decodificação e validação.
- `requirements.txt`: dependências Python.
- `tests/`: testes automatizados; `VALIDACAO.md`: resultados e roteiro de bancada.

Arduino IDE: instale **Adafruit MAX31865 library** e **Adafruit BusIO** no gerenciador de bibliotecas; use **Arduino AVR Boards >=1.8.6**. Abra `TermoGuara.ino` (o Config.h deve estar na mesma pasta), selecione Arduino Nano/ATmega328P e a porta correta. Em clones, pode ser necessário selecionar **ATmega328P (Old Bootloader)** para upload. O sketch usa Wire diretamente para ADS1115 com tempo de espera limitado; não exige biblioteca ADS adicional. Os dois programas usam **115200 baud**. Feche o Monitor Serial antes de abrir o aplicativo.

No terminal, dentro desta pasta:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe Aplicativo06.py
```

Ambiente virtual e ferramentas locais podem já estar preparados nesta entrega. Não é necessário ativar o ambiente: os comandos acima usam diretamente seu Python.

## Ligações

### Controle e sensores

| Nano | Ligação |
|---|---|
| D5 | 330 Ω → gate MOSFET câmara 1 |
| D6 | 330 Ω → gate MOSFET câmara 2 |
| D10 | CS do MAX31865 câmara 1 |
| D9 | CS do MAX31865 câmara 2 |
| D11 | MOSI/SDI dos dois MAX31865 |
| D12 | MISO/SDO dos dois MAX31865 |
| D13 | SCK dos dois MAX31865 |
| A4 | SDA dos dois ADS1115 |
| A5 | SCL dos dois ADS1115 |
| GND | Referência comum da eletrônica e negativo da fonte, retorno em estrela |

**Confira a alimentação e os níveis lógicos dos módulos MAX31865 reais**: o chip é de 3,3 V; placas Adafruit com regulador e conversores aceitam interface de 5 V, mas clones podem não aceitar. Não aplique sinais SPI de 5 V a módulos sem compatibilidade. Use conversão de nível quando necessária. Não conecte 12 V a nenhum conversor ou pino do Nano.

PT1000 em dois fios: uma ponta em cada lado do RTD. Em módulos com terminais FORCE e RTD separados, unir FORCE+ a RTD+ e FORCE− a RTD− conforme o esquema da placa. A configuração `MAX31865_2WIRE` no código **não substitui as pontes físicas**. A resistência dos cabos soma-se à do sensor e precisa entrar na calibração.

### ADS1115 e NTC

Use ADS1115 alimentados em **5 V**, com sinais I²C compatíveis com o Nano, GND comum e desacoplamento local. Configure endereços diferentes:

| Conversor | ADDR | Endereço | AIN0 | AIN1 | AIN2 | AIN3 |
|---|---|---|---|---|---|---|
| Câmara 1 | GND | 0x48 | NTC1A | NTC1B | Excitação 3,3 V | Livre |
| Câmara 2 | VDD | 0x49 | NTC2A | NTC2B | Excitação 3,3 V | Livre |

Cada NTC usa este divisor, com **seu próprio resistor fixo**:

```text
3,3 V estáveis ── Rfixo 10 kΩ ──┬── NTC 100 kΩ ── GND
                              └── AIN0 ou AIN1
3,3 V da mesma excitação ───────── AIN2
```

Não use o NTC diretamente entre 12 V e o ADC. Não inverta resistor/NTC sem alterar a equação. A excitação de 3,3 V deve ter capacidade e estabilidade verificadas; confira o regulador disponível no seu Nano/clone. AIN2 mede essa tensão em cada ADS, reduzindo a dependência de assumir exatamente 3,300 V. Leituras são sequenciais, não simultâneas; não se elimina todo ruído ou erro de ganho.

O PGA é ±6,144 V para evitar saturação perto da excitação. Essa faixa **não autoriza exceder a alimentação do ADC**: entradas operam entre GND e VDD. Excitação aceita pelo código: 2,8–3,5 V. Use pull-ups I²C adequados, considerando os já instalados nos módulos. Mantenha fios de sensores afastados do circuito de corrente das kapton.

Equações implementadas, em kelvin na etapa Beta:

```text
Rntc = Rfixo × Vntc / (Vexc − Vntc)
T°C = 1 / [1/298,15 + ln(Rntc/R25)/Beta] − 273,15
Tcorrigida = ganho × T°C + offset
```

Para R25=100 kΩ e B=3950, a resistência calculada a 90 °C é aproximadamente 9,34 kΩ. Um resistor fixo de 10 kΩ favorece a sensibilidade nessa região, em vez de usar automaticamente 100 kΩ. A escolha é de projeto, a confirmar pela calibração e pela faixa de interesse. A resistência de Thévenin também fica abaixo de 10 kΩ, reduzindo a influência da carga de entrada do ADS. Não confunda resolução nominal de 16 bits com exatidão térmica.

### Kapton e MOSFETs

```text
+12 V ─ fusível/proteção ─ corte térmico independente ─ kapton ─ drain MOSFET
                                                           source ─ GND fonte
Nano D5 ou D6 ─ 330 Ω ─ gate
                       gate ─ 10 kΩ ─ source
```

Repita para cada câmara. Confirme a pinagem no datasheet do FQP30N06L; a aba metálica está ligada ao drain e não deve encostar em outras partes condutivas inadvertidamente. A kapton é uma carga resistiva. Use bornes, fios e conexões compatíveis com corrente/temperatura; não faça o caminho de potência através do Nano ou de contatos frágeis de protoboard.

Com 10 W a 12 V: resistência nominal ≈14,4 Ω, corrente ≈0,83 A por kapton, ≈1,67 A no total a 100%. Uma fonte regulada de 12 V / 3 A oferece margem razoável para as duas, desde que confirmados os dados reais e o restante das cargas. Dimensione fusíveis para fios, conectores e corrente real. Em 50% PWM, potência média ideal ≈5 W por kapton, mas **o CSV não mede watts**.

O FQP30N06L tem resistência de condução especificada com VGS=5 V e pode atender esta carga no Nano clássico; verifique a temperatura real dos componentes. A tensão de limiar VGS(th) não serve para garantir condução plena. Alimente o Nano por USB ou por conversor regulado apropriado; não una indiscriminadamente duas fontes de 5 V. Faça retorno de potência separado até o ponto comum com a eletrônica.

## Controle e operação

- Os NTC são **sensores de realimentação**; o algoritmo PID está no Arduino. Cada malha usa a média dos dois NTC daquele bloco. O PT1000 mede o topo da amostra, não o alvo do PID nesta versão.
- Medição aproximadamente a cada **0,7–0,8 s**: espera nominal de 500 ms entre ciclos mais conversões sequenciais. O PID usa o tempo efetivamente transcorrido. Não é aquisição simultânea dos seis sensores.
- PID com derivada na medida filtrada (constante de 2 s), integração condicional e limites de saída. Unidades: Kp em PWM/°C, Ki em PWM/(°C·s), Kd em PWM·s/°C; PWM inteiro 0–255. Os valores iniciais Kp=8, Ki=0, Kd=0 são apenas ensaio inicial em controle P, não ganhos validados.
- Duração por câmara de 1 a 7200 s, contada pelo Arduino desde START aceito, incluindo aquecimento. O término desliga a câmara normalmente. A gravação continua para observar o resfriamento até o operador encerrá-la.
- A qualquer NTC/PT inválido, excesso de temperatura ou diferença NTC maior que 5 °C, a câmara desliga e retém falha. A outra pode continuar; perda de comunicação para ambas. O limite de gradiente de 5 °C precisa ser avaliado com a geometria real.
- O app envia PING ~a cada 0,8 s, somente com telemetria recente. O Nano corta após 3 s sem PING (mais latência limitada de execução); o app considera a telemetria perdida após 2 s. Comandos desconhecidos não renovam o heartbeat.
- Falha corrigida: espere os sensores abaixo de 85 °C, pressione **Rearmar falha** e depois inicie explicitamente. Não há retomada automática depois de reset/desconexão.
- Watchdog AVR opcional em `Config.h`. Ficou desabilitado porque bootloaders antigos de Nano podem ficar em ciclo de reset após watchdog. Habilite somente com bootloader testado/compatível e valide seu reset. O timeout I²C limita travamentos de barramento; software não substitui corte térmico independente.

Fluxo: conectar → conferir sensores → abrir CSV → escolher alvo, ganhos e duração → iniciar cada câmara → acompanhar → desligar/aguardar término → encerrar CSV. Abrir CSV também é possível sem aquecer. START abre o diálogo de arquivo caso não exista gravação. Os botões só liberam início após identificação, telemetria, configuração e ausência de falha.

## CSV e rastreabilidade

Arquivo UTF-8 com BOM, separador `;`, decimais com ponto (no Excel, importe escolhendo essa convenção). Contém horário ISO com fuso, tempo monotônico do PC, sequência e millis do Arduino, seis temperaturas corrigidas, dois alvos, PWM 0–255, estados, falhas, liberação e tempo restante. `nan` significa medida inválida, nunca zero. O histórico visual limita-se aos 3600 últimos quadros; o CSV preserva todos os quadros recebidos enquanto a gravação estiver aberta.

O `.csv.json` guarda configuração solicitada inicialmente e cópia do Config.h local. O `.csv.events.txt` registra comandos de controle enviados e suas confirmações/erros, inclusive parâmetros em reinícios durante a gravação. **A cópia local não comprova o conteúdo gravado no Arduino**; arquive o sketch/config efetivamente utilizados para cada ensaio. PWM é potência comandada, não medida. Flush reduz perda por encerramento do programa, mas não garante persistência contra falta de energia do computador.

Arquivos existentes não são sobrescritos; escolha outro nome. Falha de escrita causa parada/desconexão. Um ensaio pode ter lacunas de transporte; verifique a sequência no CSV. Não há retransmissão de amostras nesta versão.

## Protocolo para diagnóstico

ASCII, linhas terminadas em LF, 115200 baud, versão 1. IDs inteiros 1–65535. A interface não retransmite START automaticamente.

```text
HELLO,1                 → INFO,1,THERMOGUARA,1
PING,2                  → ACK,2,PING
START,3,1,40,8,0,0,600   → ACK,3,START ou ERR,3,motivo
OFF,4,1                 → ACK,4,OFF
STOP,5                  → ACK,5,STOP
CLR,6,1                 → ACK,6,CLR ou ERR,6,NOT_SAFE
```

START: id,câmara,alvo,Kp,Ki,Kd,duração em segundos. PING deve continuar. Firmware transmite:

```text
DATA,1,seq,ms,ntc1a,ntc1b,ntc2a,ntc2b,pt1,pt2,sp1,sp2,pwm1,pwm2,run1,run2,fault1,fault2,configured,remaining1,remaining2
```

Falhas são soma de bits: 1 NTC inválido, 2 PT inválido, 4 sobretemperatura, 8 divergência NTC, 16 perda de comunicação, 32 aquisição atrasada. STOP/OFF desligam sem apagar a falha; CLR não liga nada. Corte de fim de duração não é falha.

## Melhorias recomendadas

1. **Corte físico independente:** termostato/fusível térmico no bloco e botão de emergência interrompendo a alimentação das kapton. MOSFET pode falhar em curto, algo que PWM=0 não resolve. Escolha a temperatura conforme a margem real e a inércia, sem ultrapassar a capacidade de adesivos, sensores e amostras.
2. **Calibração na faixa de trabalho:** medir R25 e comparar cada sensor com referência conhecida em vários patamares (por exemplo 25, 40, 60, 80 °C), em ambiente isotérmico e estabilizado. Não medir resistência com o circuito energizado. Se o Beta nominal não reproduzir os pontos, ajustar Beta ou Steinhart–Hart. Ganho/offset corrige apenas parte dos erros.
3. **Montagem térmica reprodutível:** mesma profundidade e contato dos NTC, mesmo posicionamento do PT, mesma área/pressão da amostra, isolamento entre câmaras. O PT precisa estar termicamente ligado à superfície; o encapsulamento e os fios podem alterar a leitura. Dois NTC em posições diferentes também podem detectar um gradiente real, não só falha.
4. **Sintonia experimental:** iniciar com tensão das kapton desconectada para validar sensores/proteções; depois baixa potência com supervisão. Aplicar pequeno degrau, medir atraso e resposta, aumentar Kp com cautela, adicionar Ki lentamente e só depois avaliar Kd. Não realizar autotune agressivo antes de caracterizar a montagem.
5. **Rampa de alvo e critério de estabilidade:** úteis para ensaios repetíveis; são próximos aprimoramentos, não implementados nesta versão. Início da fase de medição pode ser condicionado a média dentro de uma banda e derivada pequena durante um período.
6. **Medição elétrica:** tensão/corrente por câmara, para estimar energia entregue e detectar aquecimento inesperado ou resistência desconectada. PWM sozinho não fornece fluxo térmico nem condutividade da amostra.
7. **Metrologia do experimento:** temperatura no topo e no bloco não basta, isoladamente, para extrair condutividade/resistência térmica do revestimento. É preciso modelo, espessura/área, potência/fluxo efetivo, resistências de contato, perdas laterais e incertezas. A chapa de aço e a pintura contribuem para a resposta.
8. **RTD de 3/4 fios**, se possível, reduz erro dos cabos; os PT1000 de dois fios atuais podem ser usados após calibração, com comprimento e conexões controlados. Redundância de NTC não detecta necessariamente duas leituras igualmente erradas ou ambos os sensores soltos.

## Fontes técnicas consultadas

- [Adafruit — identificação de RREF/PT100/PT1000](https://learn.adafruit.com/adafruit-max31865-rtd-pt100-amplifier/f-a-q)
- [Adafruit — ligações RTD em dois fios](https://learn.adafruit.com/adafruit-max31865-rtd-pt100-amplifier/rtd-wiring-config)
- [Adafruit — guia dos módulos MAX31865](https://learn.adafruit.com/adafruit-max31865-rtd-pt100-amplifier?view=all)
- [Texas Instruments — datasheet ADS1115](https://www.ti.com/lit/ds/symlink/ads1115.pdf)
- [onsemi — datasheet FQP30N06L](https://www.onsemi.com/download/data-sheet/pdf/fqp30n06l-d.pdf)

As escolhas de limites, resistores de divisor e estratégia PID são propostas de engenharia para esta montagem, não especificações fornecidas pelos fabricantes para o conjunto completo.
