# Verificação da entrega

Verificado em 24/09/2026. **Não foi feito upload nem ensaio com os sensores, MOSFETs ou kapton reais.** Compilação e simulação do transporte não validam eletricamente a montagem nem fazem sintonia de PID.

## Firmware

Compilado para `arduino:avr:nano` com Arduino AVR Boards 1.8.8, Adafruit MAX31865 library 1.6.2 e Adafruit BusIO 1.17.4:

- Flash: **15.314 bytes / 30.720 (49%)**.
- Variáveis globais: **846 bytes / 2.048 (41%)**; 1.202 bytes restantes para pilha/variáveis locais.
- Compilação feita com `HARDWARE_VERIFIED=false` e os parâmetros de RREF atualmente informados. Não foi gerado um firmware liberado para aquecer sem correção física.
- Bibliotecas instaladas em `.arduino/libraries`; saída de compilação em `.build/nano`.

O core AVR e o Arduino CLI já estavam disponíveis no computador. O arquivo `arduino-cli.yaml` direciona as bibliotecas desta verificação para a pasta do projeto.

## Python

Ambiente isolado `.venv`: Python 3.11, pyserial 3.5, Matplotlib 3.11.2. Verificação sintática por `py_compile` e testes com `unittest`.

**12 testes:** mapeamento dos seis sensores; NaN; rejeição de quadros truncados, versão errada, infinito e estados inseguros; limites dos comandos; detecção de reset/duplicata; rollover; identificação e apresentação na GUI; gravação/flush CSV e eventos; parada por dados vencidos; quadros fragmentados/corrompidos; reset após identificação; persistência da mensagem de comando recusado.

Os testes da GUI criam janelas ocultas e usam **porta serial simulada**, sem se conectar ao Nano.

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

## Roteiro de bancada a executar pelo operador

Comece com os **12 V das kapton desconectados**:

1. Confirmar Nano clássico 5 V; medir RREF real; resolver módulos PT100 versus PT1000. Conferir alimentação/níveis dos módulos, endereços ADS, divisores e pontes dos RTD de dois fios.
2. Comparar os seis sensores a uma referência em temperatura ambiente e vários patamares até a faixa pretendida. Ajustar parâmetros/calibração no firmware e arquivar o Config.h efetivamente gravado. Não copiar os coeficientes antigos de termopares.
3. Validar aquisição durante pelo menos vários minutos, sem saltos ou NaN; conferir correspondência física câmara/sensor e todos os campos do CSV.
4. Após configuração conferida e liberação no firmware, solicitar START e verificar D5/D6 com osciloscópio/carga de teste. Confirmar saídas independentes, limite de PWM e STOP/OFF.
5. Desconectar/curto-circuitar controladamente cada entrada NTC e abrir cada PT, **sem alimentação das kapton**. Confirmar falha, PWM zero e necessidade de rearmar. Desconectar cada ADS e simular I²C preso; confirmar ausência de espera infinita e desligamento. Não fazer curtos na alimentação.
6. Simular resistências/temperaturas perto e acima dos limites: sobretemperatura em cada sensor e diferença NTC >5 °C devem cortar a câmara correta. Verificar que o rearme exige recuperação e temperatura abaixo da margem.
7. Iniciar e retirar USB, encerrar o processo do PC, pausar heartbeat e provocar reset do Nano. Confirmar gates desligados, timeout em aproximadamente 3 s mais latência e ausência de reinício automático. Testar também o limite de duração usando 5–10 s.
8. Conferir CSV parcial após interrupção e parada por falha de escrita. Verificar dados e eventos em ambos os canais, inclusive ensaios iniciados em momentos diferentes.
9. Só então conectar potência com limitação, supervisão e corte físico instalado. Aquecer inicialmente a 35–40 °C, observar contato térmico, ruído de PWM, uniformidade, aquecimento dos MOSFETs e overshoot.
10. Sintonizar cada câmara separadamente e depois testar as duas juntas; verificar acoplamento térmico/elétrico, gradientes, inércia e desempenho até a faixa superior. Se 90 °C for limite absoluto, reduzir corte/alvo conforme o overshoot medido e dimensionar a proteção independente.

Não se pode testar por software que um MOSFET em curto interrompe a carga: a proteção física deve atuar independentemente da placa e do computador. Também não se pode concluir, apenas a partir de duas temperaturas iguais, que os sensores estejam bem acoplados ao dissipador.
