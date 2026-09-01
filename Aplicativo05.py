# TermoGuará - Interface com Calibração, WhatsApp, Cronômetro, Checagem Serial e Curva de Tendência
# Desenvolvido originalmente por Odeilson Morais Pinto / Refatorado por Gemini

import os
import sys
import time
import csv
import re
import json
import threading
import urllib.parse
import tkinter as tk
from tkinter import filedialog, messagebox
from PIL import Image
import customtkinter as ctk
import serial
import serial.tools.list_ports
import matplotlib.pyplot as plt
import matplotlib.animation as animation
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import requests
import numpy as np


def resource_path(relative_path):
    """Obtém o caminho absoluto para o recurso, funciona para dev e para o PyInstaller."""
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)


ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

def logistic_model(x, L, k, x0):
    """Modelo Logístico de 3 parâmetros: L (limite/topo), k (inclinação), x0 (ponto médio)."""
    return L / (1.0 + np.exp(-k * (x - x0)))

class TermoGuaraApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        # Janela Principal
        self.title("TermoGuará - Monitor de Temperatura")
        self.geometry("1280x950")
        self.minsize(1000, 750)
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

        # Variáveis de Estado
        self.baudrate = 9600
        self.recording = False
        self.running = True
        self.ser = None
        self.serial_thread = None
        self.time_data = []
        self.temp_data = []
        self.config_file = "calibracao_config.json"

        # Carregar configurações e calibração
        self.load_config()

        self.setup_ui()
        self.connect_serial()
        self.update_serial_status()

    def load_icon(self, relative_path, size=(18, 18)):
        try:
            caminho_completo = resource_path(relative_path)
            return ctk.CTkImage(
                light_image=Image.open(caminho_completo),
                dark_image=Image.open(caminho_completo),
                size=size
            )
        except Exception as e:
            print(f"Aviso: Não foi possível carregar o ícone '{relative_path}': {e}")
            return None

    def load_config(self):
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, "r") as f:
                    data = json.load(f)
                    self.a1 = data.get("a1", 1.02797)
                    self.b1 = data.get("b1", -1.77633)
                    self.a2 = data.get("a2", 1.03634)
                    self.b2 = data.get("b2", -2.05761)
                    self.last_calibration = data.get("last_calibration", "Não realizada")
                    self.wa_enabled = data.get("wa_enabled", False)
                    self.wa_phone = data.get("wa_phone", "")
                    self.wa_apikey = data.get("wa_apikey", "")
                    return
            except Exception:
                pass
        
        self.a1, self.b1 = 1.02797, -1.77633
        self.a2, self.b2 = 1.03634, -2.05761
        self.last_calibration = "Não realizada"
        self.wa_enabled = False
        self.wa_phone = ""
        self.wa_apikey = ""

    def save_config(self):
        data = {
            "a1": self.a1, "b1": self.b1,
            "a2": self.a2, "b2": self.b2,
            "last_calibration": self.last_calibration,
            "wa_enabled": self.wa_enabled,
            "wa_phone": self.wa_phone,
            "wa_apikey": self.wa_apikey
        }
        with open(self.config_file, "w") as f:
            json.dump(data, f, indent=4)

    def setup_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        # ------------------- 1. CABEÇALHO -------------------
        self.header_frame = ctk.CTkFrame(self, corner_radius=15, fg_color="#1E1E1E")
        self.header_frame.grid(row=0, column=0, padx=20, pady=(15, 10), sticky="ew")

        self.logo_img = self.load_icon("Termoguara.ico", size=(32, 32))
        if self.logo_img:
            self.title_label = ctk.CTkLabel(
                self.header_frame, text=" TermoGuará", image=self.logo_img,
                compound="left", font=ctk.CTkFont(size=24, weight="bold")
            )
        else:
            self.title_label = ctk.CTkLabel(
                self.header_frame, text="📈 TermoGuará", 
                font=ctk.CTkFont(size=24, weight="bold")
            )
        self.title_label.pack(side="left", padx=20, pady=12)

        self.calib_button = ctk.CTkButton(
            self.header_frame, text="⚙️ Calibração", fg_color="#37474F", hover_color="#455A64",
            width=110, command=self.open_calibration_window
        )
        self.calib_button.pack(side="left", padx=5, pady=12)

        self.wa_button = ctk.CTkButton(
            self.header_frame, text="💬 WhatsApp", fg_color="#1B5E20", hover_color="#2E7D32",
            width=110, command=self.open_whatsapp_window
        )
        self.wa_button.pack(side="left", padx=5, pady=12)

        self.check_serial_btn = ctk.CTkButton(
            self.header_frame, text="🔄 Checar Conexão", fg_color="#37474F", hover_color="#455A64",
            width=120, command=self.manual_check_serial
        )
        self.check_serial_btn.pack(side="left", padx=5, pady=12)

        self.connection_label = ctk.CTkLabel(
            self.header_frame, text="● Porta serial: Desconectado", 
            font=ctk.CTkFont(size=13, weight="bold"), text_color="#FF5252"
        )
        self.connection_label.pack(side="right", padx=20, pady=12)

        # ------------------- 2. PAINEL DE CONTROLE E TELEMETRIA -------------------
        self.dashboard_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.dashboard_frame.grid(row=1, column=0, padx=20, pady=5, sticky="ew")
        self.dashboard_frame.grid_columnconfigure((0, 1), weight=1)

        # Card de Configuração Ensaio
        self.config_card = ctk.CTkFrame(self.dashboard_frame, corner_radius=15, fg_color="#2B2B2B")
        self.config_card.grid(row=0, column=0, padx=(0, 10), pady=5, sticky="nsew")

        ctk.CTkLabel(self.config_card, text="Configuração da Análise", font=ctk.CTkFont(size=15, weight="bold")).grid(row=0, column=0, columnspan=4, padx=15, pady=(10, 5), sticky="w")

        # Linha 1: Tempo total e Intervalo
        ctk.CTkLabel(self.config_card, text="Tempo total (s):").grid(row=1, column=0, padx=(15, 5), pady=6, sticky="e")
        self.entry_total_time = ctk.CTkEntry(self.config_card, width=70)
        self.entry_total_time.insert(0, "60")
        self.entry_total_time.grid(row=1, column=1, padx=5, pady=6, sticky="w")

        ctk.CTkLabel(self.config_card, text="Intervalo (s):").grid(row=1, column=2, padx=(15, 5), pady=6, sticky="e")
        self.entry_interval = ctk.CTkEntry(self.config_card, width=70)
        self.entry_interval.insert(0, "1")
        self.entry_interval.grid(row=1, column=3, padx=(5, 15), pady=6, sticky="w")

        # Linha 2: Nome do Arquivo (Esquerda)
        ctk.CTkLabel(self.config_card, text="Nome Arquivo:").grid(row=2, column=0, padx=(15, 5), pady=6, sticky="e")
        self.entry_filename = ctk.CTkEntry(self.config_card, width=130, placeholder_text="analise_01")
        self.entry_filename.insert(0, "analise_01")
        self.entry_filename.grid(row=2, column=1, padx=5, pady=6, sticky="w")

        # Linha 2: Controles Independentes das Curvas de Tendência
        self.trend_frame = ctk.CTkFrame(self.config_card, fg_color="#1E1E1E", corner_radius=8)
        self.trend_frame.grid(row=2, column=2, columnspan=2, padx=(10, 15), pady=6, sticky="ew")

        trend_models = ["Linear", "Polinomial (2º grau)", "Exponencial", "Logarítmica", "Logística"]

        # Controle T1
        self.chk_trend_t1_var = ctk.BooleanVar(value=False)
        self.chk_trend_t1 = ctk.CTkCheckBox(
            self.trend_frame, text="Tendência T1", variable=self.chk_trend_t1_var,
            font=ctk.CTkFont(size=11, weight="bold")
        )
        self.chk_trend_t1.grid(row=0, column=0, padx=(8, 4), pady=4, sticky="w")

        self.combo_trend_t1 = ctk.CTkOptionMenu(
            self.trend_frame, values=trend_models, width=125, font=ctk.CTkFont(size=11)
        )   
        self.combo_trend_t1.grid(row=0, column=1, padx=(4, 8), pady=4, sticky="e")

        # Controle T2
        self.chk_trend_t2_var = ctk.BooleanVar(value=False)
        self.chk_trend_t2 = ctk.CTkCheckBox(
            self.trend_frame, text="Tendência T2", variable=self.chk_trend_t2_var,
            font=ctk.CTkFont(size=11, weight="bold")
        )
        self.chk_trend_t2.grid(row=1, column=0, padx=(8, 4), pady=4, sticky="w")

        self.combo_trend_t2 = ctk.CTkOptionMenu(
            self.trend_frame, values=trend_models, width=125, font=ctk.CTkFont(size=11)
        )   
        self.combo_trend_t2.grid(row=1, column=1, padx=(4, 8), pady=4, sticky="e")

        # Linha 3: Botões de Ação
        self.btn_container = ctk.CTkFrame(self.config_card, fg_color="transparent")
        self.btn_container.grid(row=3, column=0, columnspan=4, padx=15, pady=(8, 12), sticky="ew")

        self.play_button = ctk.CTkButton(
            self.btn_container, text="▶ Iniciar", fg_color="#2e7d32", hover_color="#1b5e20",
            font=ctk.CTkFont(size=14, weight="bold"), command=self.start_recording
        )
        self.play_button.pack(side="left", expand=True, fill="x", padx=5)

        self.stop_button = ctk.CTkButton(
            self.btn_container, text="⏹ Parar", fg_color="#c62828", hover_color="#b71c1c",
            font=ctk.CTkFont(size=14, weight="bold"), command=self.stop_recording
        )

        self.save_button = ctk.CTkButton(
            self.btn_container, text="💾 Salvar CSV", fg_color="#1565c0", hover_color="#0d47a1",
            font=ctk.CTkFont(size=14, weight="bold"), command=self.save_data
        )

        # Card de Telemetria
        self.telemetry_card = ctk.CTkFrame(self.dashboard_frame, corner_radius=15, fg_color="#2B2B2B")
        self.telemetry_card.grid(row=0, column=1, padx=(10, 0), pady=5, sticky="nsew")

        ctk.CTkLabel(self.telemetry_card, text="Telemetria ao Vivo", font=ctk.CTkFont(size=15, weight="bold")).pack(anchor="w", padx=15, pady=(10, 2))

        self.cards_frame = ctk.CTkFrame(self.telemetry_card, fg_color="transparent")
        self.cards_frame.pack(fill="both", expand=True, padx=15, pady=2)

        self.t1_display = ctk.CTkLabel(self.cards_frame, text="T1: -- . -- °C", font=ctk.CTkFont(size=20, weight="bold"), text_color="#00E676")
        self.t1_display.pack(side="left", expand=True)

        self.t2_display = ctk.CTkLabel(self.cards_frame, text="T2: -- . -- °C", font=ctk.CTkFont(size=20, weight="bold"), text_color="#00B0FF")
        self.t2_display.pack(side="right", expand=True)

        # Painel do Cronômetro
        self.timer_frame = ctk.CTkFrame(self.telemetry_card, fg_color="#1E1E1E", corner_radius=10)
        self.timer_frame.pack(fill="x", padx=15, pady=(2, 4))

        self.lbl_elapsed = ctk.CTkLabel(self.timer_frame, text="⏱️ Decorrido: 00:00", font=ctk.CTkFont(size=12, weight="bold"), text_color="#FFFFFF")
        self.lbl_elapsed.pack(side="left", expand=True, pady=4)

        self.lbl_remaining = ctk.CTkLabel(self.timer_frame, text="⏳ Restante: 00:00", font=ctk.CTkFont(size=12, weight="bold"), text_color="#FFB300")
        self.lbl_remaining.pack(side="right", expand=True, pady=4)

        # Exibição da Equação da Tendência
        self.lbl_equation = ctk.CTkLabel(self.telemetry_card, text="📐 Equação Tendência: -", font=ctk.CTkFont(size=11, weight="bold"), text_color="#FFD54F")
        self.lbl_equation.pack(anchor="center", pady=(2, 2))

        self.status_label = ctk.CTkLabel(self.telemetry_card, text="Aguardando início da análise...", font=ctk.CTkFont(size=11), text_color="#AAAAAA")
        self.status_label.pack(anchor="center", pady=(0, 2))

        self.last_calib_label = ctk.CTkLabel(self.telemetry_card, text=f"Última calibração em: {self.last_calibration}", font=ctk.CTkFont(size=10, slant="italic"), text_color="#888888")
        self.last_calib_label.pack(anchor="center", pady=(0, 4))

        # ------------------- 3. GRÁFICO -------------------
        self.graph_card = ctk.CTkFrame(self, corner_radius=15, fg_color="#2B2B2B")
        self.graph_card.grid(row=2, column=0, padx=20, pady=(10, 20), sticky="nsew")

        plt.style.use('dark_background')
        self.fig, self.ax = plt.subplots(figsize=(8, 4), dpi=100)
        self.fig.patch.set_facecolor('#2B2B2B')
        self.ax.set_facecolor('#1E1E1E')
        self.ax.spines['top'].set_visible(False)
        self.ax.spines['right'].set_visible(False)
        self.ax.spines['bottom'].set_color('#555555')
        self.ax.spines['left'].set_color('#555555')
        self.ax.tick_params(colors='#AAAAAA')
        self.ax.yaxis.label.set_color('#FFFFFF')
        self.ax.xaxis.label.set_color('#FFFFFF')
        self.ax.grid(True, linestyle='--', alpha=0.15, color='#FFFFFF')

        self.canvas = FigureCanvasTkAgg(self.fig, master=self.graph_card)
        self.canvas.get_tk_widget().pack(padx=15, pady=15, fill="both", expand=True)
        self.ani = animation.FuncAnimation(self.fig, self.update_plot, interval=1000, cache_frame_data=False)

    # ------------------- CÁLCULO DA CURVA DE TENDÊNCIA -------------------
    def calculate_trendline(self, x, y, model_type):
        if len(x) < 2:
            return None, "Aguardando mais dados..."
    
        x_arr = np.array(x, dtype=float)
        y_arr = np.array(y, dtype=float)

        try:
            if model_type == "Linear":
                p = np.polyfit(x_arr, y_arr, 1)
                y_fit = np.polyval(p, x_arr)
                sinal = "+" if p[1] >= 0 else "-"
                eq_text = f"y = {p[0]:.3f}x {sinal} {abs(p[1]):.2f}"
                return y_fit, eq_text

            elif model_type == "Polinomial (2º grau)":
                if len(x_arr) < 3:
                    return None, "Mínimo 3 pontos"
                p = np.polyfit(x_arr, y_arr, 2)
                y_fit = np.polyval(p, x_arr)
                eq_text = f"y = {p[0]:.2e}x² + {p[1]:.2f}x + {p[2]:.2f}"
                return y_fit, eq_text

            elif model_type == "Exponencial":
                valid = y_arr > 0
                if np.sum(valid) < 2:
                    return None, "Valores Y <= 0"
                
                p = np.polyfit(x_arr[valid], np.log(y_arr[valid]), 1)
                a = np.exp(p[1])
                b = p[0]
                y_fit = a * np.exp(b * x_arr)
                eq_text = f"y = {a:.2f} · e^({b:.3f}x)"
                return y_fit, eq_text

            elif model_type == "Logarítmica":
                valid = x_arr > 0
                if np.sum(valid) < 2:
                    return None, "Tempo X <= 0"

                p = np.polyfit(np.log(x_arr[valid]), y_arr[valid], 1)
                a, b = p[0], p[1]
                x_safe = np.where(x_arr > 0, x_arr, 1e-5)
                y_fit = a * np.log(x_safe) + b
                sinal = "+" if b >= 0 else "-"
                eq_text = f"y = {a:.2f} · ln(x) {sinal} {abs(b):.2f}"
                return y_fit, eq_text
            
            elif model_type == "Logística":
                if len(x_arr) < 3:
                    return None, "Mínimo 3 pontos"

                try:
                    max_y = np.max(y_arr)
                    if max_y <= 0:
                        return None, "Valores Y <= 0"

                    L = max_y * 1.02
                    y_safe = np.clip(y_arr, 1e-5, L - 1e-5)
                    z = np.log((L / y_safe) - 1)
                    
                    p = np.polyfit(x_arr, z, 1)
                    k = -p[0]
                    x0 = p[1] / k if k != 0 else 0

                    y_fit = L / (1.0 + np.exp(-k * (x_arr - x0)))
                    eq_text = f"y = {L:.2f} / (1 + e^(-{k:.3f}(x - {x0:.1f})))"
                    return y_fit, eq_text
                except Exception:
                    return None, "Erro no ajuste logístico"

        except Exception as e:
            return None, f"Erro: {str(e)}"

        return None, "-"

    # ------------------- SUPORTE DO CRONÔMETRO -------------------
    def format_time(self, seconds):
        m, s = divmod(max(0, int(seconds)), 60)
        return f"{m:02d}:{s:02d}"

    def update_timer_display(self, elapsed_sec, remaining_sec):
        self.lbl_elapsed.configure(text=f"⏱️ Decorrido: {self.format_time(elapsed_sec)}")
        self.lbl_remaining.configure(text=f"⏳ Restante: {self.format_time(remaining_sec)}")

    # ------------------- CONEXÃO SERIAL -------------------
    def connect_serial(self):
        ports = list(serial.tools.list_ports.comports())
        if ports:
            port = ports[0].device
            try:
                self.ser = serial.Serial(port, self.baudrate, timeout=1)
            except Exception:
                self.ser = None

    def update_serial_status(self):
        if self.ser is None or not self.ser.is_open:
            self.connection_label.configure(text="● Porta serial: Desconectado", text_color="#FF5252")
        else:
            self.connection_label.configure(text=f"● Porta serial: {self.ser.port}", text_color="#00E676")
        self.after(1000, self.update_serial_status)

    def manual_check_serial(self):
        if self.ser and self.ser.is_open:
            messagebox.showinfo("Status da Conexão", f"Conexão ativa e operando normalmente na porta {self.ser.port}.")
            return

        self.connect_serial()
        if self.ser and self.ser.is_open:
            messagebox.showinfo("Sucesso", f"Dispositivo encontrado e conectado com sucesso na porta {self.ser.port}!")
        else:
            messagebox.showwarning("Aviso de Conexão", "Nenhum dispositivo serial válido foi detectado. Verifique o cabo USB.")

    # ------------------- EXECUÇÃO DA ANÁLISE -------------------
    def start_recording(self):
        if self.recording: return
        
        try:
            self.total_time = int(self.entry_total_time.get())
            self.sample_interval = int(self.entry_interval.get())
        except ValueError:
            messagebox.showerror("Erro", "Use valores numéricos válidos.")
            return

        self.time_data.clear()
        self.temp_data.clear()
        self.ax.clear()
        self.ax.grid(True, linestyle='--', alpha=0.15, color='#FFFFFF')
        self.canvas.draw()

        self.update_timer_display(0, self.total_time)

        self.recording = True
        self.play_button.pack_forget()
        self.save_button.pack_forget()
        self.stop_button.pack(side="left", expand=True, fill="x", padx=5)

        self.status_label.configure(text="Gravando dados e aquecendo...", text_color="#00E676")

        # --> ADICIONE ESTA VERIFICAÇÃO PARA LIGAR AS CHAPAS <--
        if self.ser and self.ser.is_open:
            self.ser.write(b'ON\n')
            time.sleep(0.1) # Breve pausa para o Arduino processar
            self.ser.reset_input_buffer()

        self.serial_thread = threading.Thread(target=self.read_serial, daemon=True)
        self.serial_thread.start()

    def read_serial(self):
        start_time = time.time()
        next_sample_time = start_time

        while self.recording and self.running:
            try:
                if self.ser is None or not self.ser.is_open:
                    self.after(0, lambda: self.status_label.configure(text="Erro: Porta desconectada.", text_color="#FF5252"))
                    self.after(0, self.stop_recording)
                    break

                now = time.time()
                elapsed = now - start_time
                remaining = max(0, self.total_time - elapsed)

                self.after(0, lambda e=elapsed, r=remaining: self.update_timer_display(e, r))

                if elapsed > self.total_time + 0.1:
                    self.recording = False
                    self.after(0, self.analysis_completed)
                    break

                if now >= next_sample_time:
                    self.ser.reset_input_buffer()
                    self.ser.write(b'R\n')
                    time.sleep(0.1)

                    data = self.ser.readline().decode('utf-8').strip()
                    matches = re.findall(r'-?\d+(?:\.\d+)?', data)

                    if len(matches) >= 2:
                        t1 = self.a1 * float(matches[0]) + self.b1
                        t2 = self.a2 * float(matches[1]) + self.b2
                        elapsed_round = round(elapsed, 1)
                        
                        self.time_data.append(elapsed_round)
                        self.temp_data.append((t1, t2))

                        self.after(0, lambda v1=t1: self.t1_display.configure(text=f"T1: {v1:.2f} °C"))
                        self.after(0, lambda v2=t2: self.t2_display.configure(text=f"T2: {v2:.2f} °C"))

                    next_sample_time += self.sample_interval

                time.sleep(0.01)

            except Exception as e:
                self.after(0, lambda err=str(e): self.status_label.configure(text=f"Erro: {err}", text_color="#FF5252"))
                self.after(0, self.stop_recording)
                break

    def stop_recording(self):
        self.recording = False
        self.stop_button.pack_forget()
        self.play_button.pack(side="left", expand=True, fill="x", padx=5)
        
        # --> ADICIONE ESTA VERIFICAÇÃO PARA DESLIGAR AS CHAPAS <--
        if self.ser and self.ser.is_open:
            self.ser.write(b'OFF\n')
            time.sleep(0.1)

    def analysis_completed(self):
        self.stop_recording()
        self.update_timer_display(self.total_time, 0)
        self.save_button.pack(side="left", expand=True, fill="x", padx=5)
        self.status_label.configure(text="Análise concluída com sucesso!", text_color="#00E676")

        if self.wa_enabled and self.wa_phone and self.wa_apikey:
            nome_arq = self.entry_filename.get().strip() or "analise"
            ultimo_t1 = f"{self.temp_data[-1][0]:.2f}" if self.temp_data else "--"
            ultimo_t2 = f"{self.temp_data[-1][1]:.2f}" if self.temp_data else "--"
            
            msg = (
                f"🧪 *TermoGuará - Ensaio Concluído!*\n\n"
                f"📌 *Arquivo:* {nome_arq}\n"
                f"⏱️ *Duração:* {self.total_time}s\n"
                f"🌡️ *Temp Final T1:* {ultimo_t1} °C\n"
                f"🌡️ *Temp Final T2:* {ultimo_t2} °C"
            )
            
            threading.Thread(
                target=self.send_whatsapp, 
                args=(self.wa_phone, self.wa_apikey, msg), 
                daemon=True
            ).start()

        messagebox.showinfo("Análise Concluída", "A coleta de dados foi finalizada com sucesso!")

    # ------------------- WHATSAPP E CALIBRAÇÃO -------------------
    def open_whatsapp_window(self):
        wa_win = ctk.CTkToplevel(self)
        wa_win.title("Notificação via WhatsApp")
        wa_win.geometry("460x420")
        wa_win.resizable(False, False)
        wa_win.grab_set()

        ctk.CTkLabel(wa_win, text="💬 Notificação via WhatsApp", font=ctk.CTkFont(size=16, weight="bold")).pack(pady=(15, 5))
        ctk.CTkLabel(wa_win, text="Receba um aviso no celular quando o ensaio terminar.", font=ctk.CTkFont(size=12), text_color="#AAAAAA").pack(pady=(0, 10))

        switch_var = ctk.BooleanVar(value=self.wa_enabled)
        switch_wa = ctk.CTkSwitch(wa_win, text="Ativar avisos via WhatsApp", variable=switch_var, font=ctk.CTkFont(size=13, weight="bold"))
        switch_wa.pack(pady=10)

        card_wa = ctk.CTkFrame(wa_win, corner_radius=10)
        card_wa.pack(padx=20, pady=10, fill="x")

        ctk.CTkLabel(card_wa, text="Número Telefone (com DDD):").pack(anchor="w", padx=15, pady=(10, 2))
        entry_phone = ctk.CTkEntry(card_wa, placeholder_text="Ex: 5511999999999")
        entry_phone.pack(fill="x", padx=15, pady=(0, 10))
        entry_phone.insert(0, self.wa_phone)

        ctk.CTkLabel(card_wa, text="API Key CallMeBot:").pack(anchor="w", padx=15, pady=(5, 2))
        entry_key = ctk.CTkEntry(card_wa, placeholder_text="Ex: 123456", show="*")
        entry_key.pack(fill="x", padx=15, pady=(0, 15))
        entry_key.insert(0, self.wa_apikey)

        def testar_envio():
            phone = entry_phone.get().strip()
            key = entry_key.get().strip()
            if not phone or not key:
                messagebox.showwarning("Aviso", "Preencha o número e a API Key antes de testar.")
                return

            def run_test():
                ok, err = self.send_whatsapp(phone, key, "🧪 TermoGuará: Teste de notificação configurado com sucesso!")
                if ok:
                    self.after(0, lambda: messagebox.showinfo("Sucesso", "Mensagem de teste enviada para o seu WhatsApp!"))
                else:
                    self.after(0, lambda: messagebox.showerror("Erro de Envio", f"Falha ao enviar:\n{err}"))

            threading.Thread(target=run_test, daemon=True).start()

        def salvar_wa():
            self.wa_enabled = switch_var.get()
            self.wa_phone = entry_phone.get().strip()
            self.wa_apikey = entry_key.get().strip()
            self.save_config()
            messagebox.showinfo("Sucesso", "Configurações do WhatsApp salvas!")
            wa_win.destroy()

        btn_box = ctk.CTkFrame(wa_win, fg_color="transparent")
        btn_box.pack(fill="x", padx=20, pady=10)

        btn_test = ctk.CTkButton(btn_box, text="🧪 Testar", fg_color="#37474F", hover_color="#455A64", width=100, command=testar_envio)
        btn_test.pack(side="left", padx=5)

        btn_save = ctk.CTkButton(btn_box, text="💾 Salvar Configurações", fg_color="#1B5E20", hover_color="#2E7D32", command=salvar_wa)
        btn_save.pack(side="right", expand=True, fill="x", padx=5)

    def send_whatsapp(self, phone, apikey, text):
        try:
            phone_clean = phone.replace("+", "").replace(" ", "").replace("-", "")
            text_encoded = urllib.parse.quote(text)
            url = f"https://api.callmebot.com/whatsapp.php?phone={phone_clean}&text={text_encoded}&apikey={apikey}"

            res = requests.get(url, timeout=10)
            if res.status_code == 200:
                return True, "OK"
            else:
                detalhe = res.text.strip() if res.text else f"HTTP Status {res.status_code}"
                return False, detalhe
        except Exception as e:
            return False, str(e)

    def open_calibration_window(self):
        calib_win = ctk.CTkToplevel(self)
        calib_win.title("Calibração de Sensores")
        calib_win.geometry("450x420")
        calib_win.resizable(False, False)
        calib_win.grab_set()

        ctk.CTkLabel(calib_win, text="⚙️ Ajuste de Calibração (y = ax + b)", font=ctk.CTkFont(size=16, weight="bold")).pack(pady=(15, 5))
        ctk.CTkLabel(calib_win, text="Corrija os valores com base em um termopar calibrado.", font=ctk.CTkFont(size=12), text_color="#AAAAAA").pack(pady=(0, 15))

        f_t1 = ctk.CTkFrame(calib_win, corner_radius=10)
        f_t1.pack(padx=20, pady=5, fill="x")
        ctk.CTkLabel(f_t1, text="Sensor T1", font=ctk.CTkFont(weight="bold"), text_color="#00E676").grid(row=0, column=0, columnspan=4, padx=10, pady=5, sticky="w")
        
        ctk.CTkLabel(f_t1, text="Ganho (a1):").grid(row=1, column=0, padx=5, pady=5)
        entry_a1 = ctk.CTkEntry(f_t1, width=90)
        entry_a1.insert(0, str(self.a1))
        entry_a1.grid(row=1, column=1, padx=5, pady=5)

        ctk.CTkLabel(f_t1, text="Offset (b1):").grid(row=1, column=2, padx=5, pady=5)
        entry_b1 = ctk.CTkEntry(f_t1, width=90)
        entry_b1.insert(0, str(self.b1))
        entry_b1.grid(row=1, column=3, padx=5, pady=5)

        f_t2 = ctk.CTkFrame(calib_win, corner_radius=10)
        f_t2.pack(padx=20, pady=10, fill="x")
        ctk.CTkLabel(f_t2, text="Sensor T2", font=ctk.CTkFont(weight="bold"), text_color="#00B0FF").grid(row=0, column=0, columnspan=4, padx=10, pady=5, sticky="w")

        ctk.CTkLabel(f_t2, text="Ganho (a2):").grid(row=1, column=0, padx=5, pady=5)
        entry_a2 = ctk.CTkEntry(f_t2, width=90)
        entry_a2.insert(0, str(self.a2))
        entry_a2.grid(row=1, column=1, padx=5, pady=5)

        ctk.CTkLabel(f_t2, text="Offset (b2):").grid(row=1, column=2, padx=5, pady=5)
        entry_b2 = ctk.CTkEntry(f_t2, width=90)
        entry_b2.insert(0, str(self.b2))
        entry_b2.grid(row=1, column=3, padx=5, pady=5)

        def save_new_calibration():
            try:
                self.a1 = float(entry_a1.get().replace(',', '.'))
                self.b1 = float(entry_b1.get().replace(',', '.'))
                self.a2 = float(entry_a2.get().replace(',', '.'))
                self.b2 = float(entry_b2.get().replace(',', '.'))
                
                self.last_calibration = time.strftime("%d/%m/%Y")
                self.save_config()
                self.last_calib_label.configure(text=f"Última calibração em: {self.last_calibration}")
                
                messagebox.showinfo("Sucesso", "Parâmetros de calibração salvos com sucesso!")
                calib_win.destroy()
            except ValueError:
                messagebox.showerror("Erro de Formato", "Por favor, insira apenas valores numéricos válidos.")

        btn_save = ctk.CTkButton(
            calib_win, text="💾 Salvar Calibração", fg_color="#1565c0", hover_color="#0d47a1",
            font=ctk.CTkFont(size=13, weight="bold"), command=save_new_calibration
        )
        btn_save.pack(pady=15)

    def save_data(self):
        nome_arquivo = self.entry_filename.get().strip()
        if not nome_arquivo:
            nome_arquivo = "dados_temperatura"
            
        directory = filedialog.askdirectory(title="Escolha o diretório para salvar o CSV")
        if not directory: return
        
        filepath = os.path.join(directory, f"{nome_arquivo}.csv")
        
        with open(filepath, 'w', newline='') as csvfile:
            writer = csv.writer(csvfile, delimiter=';')
            writer.writerow(['Tempo (s)', 'T1 (°C)', 'T2 (°C)', time.strftime("%d/%m/%Y %H:%M:%S")])
            for t, (t1, t2) in zip(self.time_data, self.temp_data):
                writer.writerow([t, t1, t2])
                
        messagebox.showinfo("Salvo", f"Dados salvos em:\n{filepath}")
        self.save_button.pack_forget()

    # ------------------- ATUALIZAÇÃO DO GRÁFICO -------------------
    def update_plot(self, frame):
        self.ax.clear()
        self.ax.grid(True, linestyle='--', alpha=0.15, color='#FFFFFF')
        
        if self.temp_data:
            min_len = min(len(self.time_data), len(self.temp_data))
            tempos = self.time_data[:min_len]
            t1 = [v[0] for v in self.temp_data[:min_len]]
            
            has_t2 = any(v[1] != 0.0 for v in self.temp_data[:min_len])
            t2 = [v[1] for v in self.temp_data[:min_len]] if has_t2 else []

            # Plot do Sensor T2 (se houver dados)
            if has_t2:
                self.ax.plot(tempos, t2, label='T2', color='#00B0FF', linewidth=2, marker='o', markersize=3)

            # Plot do Sensor T1
            self.ax.plot(tempos, t1, label='T1', color='#00E676', linewidth=2, marker='o', markersize=3)

            # --- PROCESSAMENTO DAS CURVAS DE TENDÊNCIA INDEPENDENTES ---
            eq_text_t1 = "-"
            if self.chk_trend_t1_var.get() and len(tempos) >= 2:
                tipo_t1 = self.combo_trend_t1.get()
                y_fit_t1, eq_t1 = self.calculate_trendline(tempos, t1, tipo_t1)

                if y_fit_t1 is not None:
                    self.ax.plot(tempos, y_fit_t1, label=f'Tendência T1 ({tipo_t1})', color='#FFD54F', linestyle='--', linewidth=2)
                eq_text_t1 = eq_t1

            eq_text_t2 = "-"
            if self.chk_trend_t2_var.get() and has_t2 and len(tempos) >= 2:
                tipo_t2 = self.combo_trend_t2.get()
                y_fit_t2, eq_t2 = self.calculate_trendline(tempos, t2, tipo_t2)

                if y_fit_t2 is not None:
                    self.ax.plot(tempos, y_fit_t2, label=f'Tendência T2 ({tipo_t2})', color='#FF8A65', linestyle='--', linewidth=2)
                eq_text_t2 = eq_t2

            # Atualização da exibição das equações
            eq_info = []
            if self.chk_trend_t1_var.get():
                eq_info.append(f"T1: {eq_text_t1}")
            if self.chk_trend_t2_var.get():
                eq_info.append(f"T2: {eq_text_t2}")

            if eq_info:
                self.lbl_equation.configure(text="📐 " + " | ".join(eq_info))
            else:
                self.lbl_equation.configure(text="📐 Equação Tendência: Desativada")

            self.ax.legend(facecolor='#1E1E1E', edgecolor='none')

        self.ax.set_xlabel("Tempo (s)", color='#FFFFFF')
        self.ax.set_ylabel("Temperatura (°C)", color='#FFFFFF')

    def on_closing(self):
        self.running = False
        self.recording = False
        if self.serial_thread and self.serial_thread.is_alive():
            self.serial_thread.join(timeout=0.5)
        if self.ser and self.ser.is_open:
            self.ser.close()
        self.destroy()


if __name__ == "__main__":
    app = TermoGuaraApp()
    app.mainloop()