#pragma once

// CONFIRA TODOS os valores e a montagem antes de mudar para true.
// Os valores abaixo são exemplos, NÃO uma caracterização dos seus sensores.
constexpr bool HARDWARE_VERIFIED = false;
constexpr bool USE_WATCHDOG = false; // Só habilite com bootloader compatível, veja README.
constexpr float NTC_R25[4] = {100000, 100000, 100000, 100000};
constexpr float NTC_BETA[4] = {3950, 3950, 3950, 3950};
constexpr float SERIES_R[4] = {10000, 10000, 10000, 10000};
// Valor ATUAL informado (marcação 431 = 430 ohms): inadequado para PT1000.
// Substitua os módulos/resistores por 4.3 kOhm e atualize ESTES valores medidos.
constexpr float PT_RREF[2] = {430, 430};
// Correção em °C: Tcorrigida = ganho * Tconvertida + offset.
// Ordem: NTC1A, NTC1B, NTC2A, NTC2B, PT1, PT2.
constexpr float CAL_GAIN[6] = {1, 1, 1, 1, 1, 1};
constexpr float CAL_OFFSET[6] = {0, 0, 0, 0, 0, 0};
constexpr float MIN_VALID_C = -20;
constexpr float MAX_VALID_C = 150;
constexpr float MAX_TEMP_C = 90; // Corte por QUALQUER sensor da câmara.
constexpr float MIN_SETPOINT_C = 5;
constexpr float MAX_SETPOINT_C = 85;
constexpr float MAX_NTC_DELTA_C = 5;
constexpr uint8_t MAX_PWM = 128; // Limite inicial ~50%; não é medição de potência.
constexpr uint32_t SAMPLE_MS = 500;
constexpr uint32_t LINK_TIMEOUT_MS = 3000;
constexpr uint32_t MAX_RUN_S = 7200;
static_assert(!HARDWARE_VERIFIED || (PT_RREF[0]>1000 && PT_RREF[1]>1000),
              "PT1000 exige RREF adequado: substitua 430 ohms e atualize Config.h.");
static_assert(MAX_SETPOINT_C < MAX_TEMP_C, "O alvo deve ficar abaixo do corte.");
