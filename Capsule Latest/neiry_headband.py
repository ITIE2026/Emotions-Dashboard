# Python 3.11.9
# matplotlib==3.10.8
# mne==1.11.0
# numpy==2.4.1
# pandas==3.0.0
# pyEDFlib==0.1.42
# pyinstaller==6.18.0
# pyinstaller-hooks-contrib==2026.0
# pyneurosdk2==1.0.15
# scipy==1.17.0
# setuptools==65.5.0

import tkinter as tk
from tkinter import messagebox
import random
import threading
import time
from collections import deque
from pvrecorder import PvRecorder
import wave
import datetime
import numpy as np
from neurosdk.scanner import Scanner
from neurosdk.cmn_types import *
from collections import deque
import struct
from scipy.signal import butter, lfilter
import pyedflib
import os

import warnings
warnings.filterwarnings("ignore", category=RuntimeWarning) 
warnings.filterwarnings("ignore", category=DeprecationWarning) 

if not os.path.isdir('data'):
    os.mkdir('data')

class EEGApp:
    def __init__(self, root):

        self.now_timestamp = datetime.datetime.now()
        self.now = self.now_timestamp.strftime("%Y-%m-%d_%H-%M-%S")
        
        self.root = root
        self.root.title("Headband and micro. Connect, record.")
        self.root.geometry("400x300")
        # self.root.iconbitmap('photo.ico')  # Add your icon file here

        # Style improvements
        self.root.configure(bg="#f4f4f4")

        # Placeholders for resistance and battery charge
        self.resistance_label = tk.Label(root, text="Resistance: N/A", anchor="w")
        self.resistance_label.place(x=10, y=10)

        self.battery_label = tk.Label(root, text="Battery: N/A", anchor="e")
        self.battery_label.place(x=300, y=10)

        # Buttons
        self.connect_button = tk.Button(root, text="Connect to the device", command=self.connect_device, state=tk.NORMAL)
        self.connect_button.place(relx=0.5, rely=0.3, anchor="center", width=150)

        self.start_button = tk.Button(root, text="Start recording", command=self.start_recording, state=tk.DISABLED)
        self.start_button.place(relx=0.5, rely=0.5, anchor="center", width=150)

        self.stop_button = tk.Button(root, text="Stop recording", command=self.stop_recording, state=tk.DISABLED)
        self.stop_button.place(relx=0.5, rely=0.7, anchor="center", width=150)

        self.sensor_band = None
        self.resist_data = deque(maxlen=1200000)
        self.eeg_data = deque(maxlen=1200000)
        self.ppg_data = deque(maxlen=1200000)
        self.mems_data = deque(maxlen=1200000)

        self.recorder = PvRecorder(device_index=-1, frame_length=512)
        self.audio = []

        self.recording = False

    def connect_device(self):
        scanner = Scanner([SensorFamily.LEHeadband])
        scanner.start()
        while scanner.sensors() == []:
            pass
        scanner.stop()
        sensors = scanner.sensors()
        sensor = sensors[0]
        
        def sensorFound(scanner, sensors):
           for i in range(len(sensors)):
               print('Sensor %s' % sensors[i])
        
        scanner.sensorsChanged = sensorFound
        sn = sensor.SerialNumber
        sensor_band = scanner.create_sensor(sensor)
        self.sensor_band = sensor_band
        self.sensor_band.red_amplitude = RedAmplitude.RedAmp42
        
        messagebox.showinfo("Success", f"Device SerialNumber:{sn} connected successfully!", icon='info')
        
        self.check_resistance()
        threading.Thread(target=self.update_resistance, daemon=True).start()
        threading.Thread(target=self.update_battery, daemon=True).start()

    def check_resistance(self):
        resist_data = self.resist_data
        def on_resist_data_received(sensor_band, data):
            resist_data.append(data)                
        self.sensor_band.resistDataReceived = on_resist_data_received
        self.sensor_band.exec_command(SensorCommand.StartResist)
        
        self.connect_button.config(state=tk.DISABLED)
        self.start_button.config(state=tk.NORMAL)

    def update_resistance(self):
        while len(self.resist_data) == 0:
            pass
            
        while not self.recording:
            
            resistance = self.resist_data[-1]
            battery = self.sensor_band.batt_power

            self.resistance_label.config(text=f"Resistance:\nT3:{resistance.T3 / 1000:.2f} kΩ, T4:{resistance.T4 / 1000:.2f} kΩ\nO1:{resistance.O1 / 1000:.2f} kΩ, O2:{resistance.O2 / 1000:.2f} kΩ")
            self.battery_label.config(text=f"Battery: {battery}%")

            if self.recording:
                break

    def update_battery(self):
        battery = self.sensor_band.batt_power
        self.battery_label.config(text=f"Battery: {battery}%")

    def record_sound(self):
        
        self.recorder.start()
        
        while True:
            frame = self.recorder.read()
            self.audio.extend(frame)

            if self.recording == False:
                break

    def check_recording(self):

        while True:

            n_eeg = len(self.eeg_data)
            n_ppg = len(self.ppg_data)
            n_mems = len(self.mems_data)
            n_audio = len(self.audio)
            
            current = time.time()
            while time.time() < current + 2:
                pass

            n_eeg_new = len(self.eeg_data)
            n_ppg_new = len(self.ppg_data)
            n_mems_new = len(self.mems_data)
            n_audio_new = len(self.audio)

            if (n_eeg_new - n_eeg) == 0:
                messagebox.showinfo("Problem", f"Headband disconnected! Restart the app", icon='error')
            elif (n_ppg_new - n_ppg) == 0:
                messagebox.showinfo("Problem", f"Headband disconnected! Restart the app", icon='error')
            elif (n_mems_new - n_mems) == 0:
                messagebox.showinfo("Problem", f"Headband disconnected! Restart the app", icon='error')
            elif (n_audio_new - n_audio) == 0:
                messagebox.showinfo("Problem", f"Audio stopped recording! Restart the app", icon='error')

            if self.recording == False:
                break
            

    def start_recording(self):

        self.recording = True

        self.sensor_band.exec_command(SensorCommand.StopResist)
        
        eeg_data = self.eeg_data
        def on_eeg_data_received(sensor_band, data):
            raw_data = [[i.T3, i.T4, i.O1, i.O2] for i in data] 
            eeg_data.extend(raw_data)

        self.sensor_band.signalDataReceived = on_eeg_data_received
        self.sensor_band.exec_command(SensorCommand.StartSignal)

        ppg_data = self.ppg_data 
        def on_ppg_data_received(sensor_band, data):
            ppg_data.extend([i.RedAmplitude for i in data])
            
        self.sensor_band.fpgDataReceived = on_ppg_data_received
        self.sensor_band.exec_command(SensorCommand.StartFPG)

        mems_data = self.mems_data
        def on_mems_data_received(sensor_band, data):
            mems_data.extend(data)
        self.sensor_band.memsDataReceived = on_mems_data_received
        self.sensor_band.exec_command(SensorCommand.StartMEMS)

        threading.Thread(target=self.record_sound, daemon=True).start()
        threading.Thread(target=self.check_recording, daemon=True).start()
        
        messagebox.showinfo("Success", "Recording started.", icon='info')
        self.start_button.config(state=tk.DISABLED)
        self.stop_button.config(state=tk.NORMAL)
        

    def stop_recording(self):
        # Placeholder for stopping recording logic
        self.recording = False

        self.sensor_band.disconnect()
        self.recorder.stop()
        
        path = f'data/{self.now}_audio.wav' 
        with wave.open(path, 'w') as f:
            f.setparams((1, 2, 16000, 512, "NONE", "NONE"))
            f.writeframes(struct.pack("h" * len(self.audio), *self.audio))
        self.recorder.delete()

        path = f'data/{app.now}_eeg.csv' 
        np.savetxt(path, np.concatenate([np.arange(len(self.eeg_data))[:, None] / 250, np.array(self.eeg_data)], axis=1),
                   header=','.join(['time (s)', 'T3', 'T4', 'O1', 'O2']), delimiter=',', comments='', fmt='%.3f' + ',%.16f'*4)

        channelNames = ['T3', 'T4', 'O1', 'O2']

        file_type = pyedflib.FILETYPE_BDF
        f_eeg = pyedflib.EdfWriter(f'data/{self.now}_eeg.bdf',
                                   n_channels=len(channelNames), 
                                   file_type=file_type)

        dmin, dmax = -8388608, 8388607
        channel_info = []
        data = np.array(self.eeg_data)
        fs = 250

        for i, label in enumerate(channelNames):

            ch_dict = {'label': label, 
                       'dimension': 'mV', 
                       'sample_frequency': fs, 
                       'physical_min': data[:, i].min(), 
                       'physical_max': data[:, i].max(), 
                       'digital_min':  dmin, 
                       'digital_max':  dmax, 
                       'transducer': '', 
                       'prefilter': ''}
            channel_info.append(ch_dict)

        f_eeg.setSignalHeaders(channel_info)
        f_eeg.setStartdatetime(self.now_timestamp)
        f_eeg.writeSamples(data.T)

        f_eeg.close()

        lowcut = 4
        highcut = 30
        fs = 250
        order = 4
        nyquist = 0.5 * fs
        low = lowcut / nyquist
        high = highcut / nyquist
        b, a = butter(order, [low, high], btype='band')

        eeg_data_filt = lfilter(b, a, np.array(self.eeg_data), axis=0)
        path = f'data/{self.now}_eeg_filt.csv' 
        np.savetxt(path, np.concatenate([np.arange(len(eeg_data_filt))[:, None] / 250, eeg_data_filt], axis=1),
                   header=','.join(['time (s)', 'T3', 'T4', 'O1', 'O2']), delimiter=',', comments='', fmt='%.3f' + ',%.16f'*4)



        file_type = pyedflib.FILETYPE_BDF
        f_eeg = pyedflib.EdfWriter(f'data/{self.now}_eeg_filt.bdf',
                                   n_channels=len(channelNames), 
                                   file_type=file_type)

        dmin, dmax = -8388608, 8388607
        channel_info = []
        data = eeg_data_filt

        for i, label in enumerate(channelNames):

            ch_dict = {'label': label, 
                       'dimension': 'mV', 
                       'sample_frequency': fs, 
                       'physical_min': data[:, i].min(), 
                       'physical_max': data[:, i].max(), 
                       'digital_min':  dmin, 
                       'digital_max':  dmax, 
                       'transducer': '', 
                       'prefilter': ''}
            channel_info.append(ch_dict)

        f_eeg.setSignalHeaders(channel_info)
        f_eeg.setStartdatetime(self.now_timestamp)
        f_eeg.writeSamples(data.T)

        f_eeg.close()
        

        path = f'data/{self.now}_ppg.csv' 
        np.savetxt(path, np.concatenate([np.arange(len(self.ppg_data))[:, None] / 100, np.array(self.ppg_data)[:, None]], axis=1), 
                   header=','.join(['time (s)', 'PPG']), delimiter=',', comments='', fmt='%.3f,%i')

        path = f'data/{self.now}_resist_before_recording.csv' 
        np.savetxt(path, np.array([[i.T3, i.T4, i.O1, i.O2] for i in self.resist_data])[-1][None], 
                   header=','.join(['T3', 'T4', 'O1', 'O2']), delimiter=',', comments='', fmt='%.1f')

        path = f'data/{self.now}_mems.csv' 
        np.savetxt(path, 
                   np.concatenate([np.arange(len(self.mems_data))[:, None] / 250, 
                                   np.array([[i.Gyroscope.X, i.Gyroscope.Y, i.Gyroscope.Z,
                                              i.Accelerometer.X, i.Accelerometer.Y, i.Accelerometer.Z] for i in self.mems_data])], 
                                  axis=1), 
                   header=','.join(['time (s)', 'Gyroscope_X', 'Gyroscope_Y', 'Gyroscope_Z', 'Accelerometer_X', 'Accelerometer_Y', 'Accelerometer_Z']), 
                   comments='', fmt='%.3f' + ',%.16f'*6, delimiter=',')
        
        messagebox.showinfo("Success", "Recording stopped.", icon='info')
        self.stop_button.config(state=tk.DISABLED)
        self.connect_button.config(state=tk.DISABLED)
        self.start_button.config(state=tk.DISABLED)
        self.running = False

root = tk.Tk()
app = EEGApp(root)
root.mainloop()