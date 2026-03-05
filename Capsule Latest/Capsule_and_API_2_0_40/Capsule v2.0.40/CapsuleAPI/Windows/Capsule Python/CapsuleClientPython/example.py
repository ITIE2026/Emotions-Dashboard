from Capsule import Capsule
from DeviceLocator import DeviceLocator
from DeviceType import DeviceType
from Error import Error
from Device import Device, Device_Connection_Status
from PSDData import PSDData
from Calibrator import *
from time import sleep
from Emotions import Emotions, Emotions_States
from Cardio import Cardio, Cardio_Data


device_locator = None
psd_freqs = None

class EventFiredState:
    def __init__(self):
        self._awake = False
    
    def is_awake(self):
        return self._awake

    def set_awake(self):
        self._awake = True
    
    def sleep(self):
        self._awake = False


def non_blocking_cond_wait(wake_event : EventFiredState, event_name: str, total_sleep_time: int):
    print("Waiting {name} for {time} seconds...".format(name = event_name, time = total_sleep_time))
    global device_locator
    total_sleep_time *= 50
    for _ in range(total_sleep_time):
        if device_locator is not None:
            device_locator.update()
        if wake_event.is_awake():
            print("Event {name} occurred!".format(name = event_name))
            return
        
        sleep(.02)
    
    print("Waiting for {event} timeout".format(event = event_name))


device_list_event_fired = EventFiredState()
device = None
def on_device_list(locator: DeviceLocator, info: DeviceLocator.DeviceInfoList, fail_reason: DeviceLocator.FailReason) -> None:
    print("Found {count} devices".format(count = len(info)))
    print('-' * 30)
    if len(info) == 0:
        return
    
    for i in range(len(info)):
        print("{i} device:".format(i = i))
        err = Error()
        device_info = info[i]
        print("Serial:     {s}".format(s = device_info.get_serial()))
        print("Name:       {n}".format(n = device_info.get_name()))
        print("Type:       {t}".format(t = device_info.get_type()))
        print('-' * 30)

    print("For this example we'll stick with 0 device")

    global device
    device = Device(locator, info[0].get_serial(), locator.get_lib())
    device_list_event_fired.set_awake()


device_connection_state_fired = EventFiredState()
def on_connection_status_changed(device: Device, status: Device_Connection_Status):
    print('Device connection status changed: {s}!'.format(s = status))
    device_connection_state_fired.set_awake()

device_psd_fired = EventFiredState()
def on_psd(device: Device, psd: PSDData):
    global psd_freqs
    freqs_indicies = range(psd.get_frequencies_count())
    if not device_psd_fired.is_awake():
        psd_freqs = [psd.get_frequency(freqIdx) for freqIdx in freqs_indicies]
        print('PSD FREQS:', psd_freqs)
        device_psd_fired.set_awake()
    for idx in range(psd.get_channels_count()):
        psd_channel = []
        for freqIdx in freqs_indicies:
            val = psd.get_psd(idx, freqIdx)
            psd_channel.append(val)
        print(f"PSD ch={idx} {dict(zip(psd_freqs[::100], psd_channel[::100]))}")
    

def on_emotions_states(emotion: Emotions, emotion_states: Emotions_States):
    print(f"Emotions_States(timestampMilli={emotion_states.timestampMilli} focus={emotion_states.focus} chill={emotion_states.chill} stress={emotion_states.stress} anger={emotion_states.anger} selfControl={emotion_states.selfControl})")


def on_cardio_indexes(cardio: Cardio, indexes: Cardio_Data):
    print(f"Cardio_Data(timestampMilli={indexes.timestampMilli} heartRate={indexes.heartRate} stressIndex={indexes.stressIndex} kaplanIndex={indexes.kaplanIndex} hasArtifacts={indexes.hasArtifacts} skinContact={indexes.skinContact}) motionArtifacts={indexes.motionArtifacts} metricsAvailable={indexes.metricsAvailable}")


def main():
    capsuleLib = Capsule('.\\CapsuleClient.dll')    # Connect the library. (For macOS use .\\libCapsuleClient.dylib, for Linux .\\libCapsuleClient.so)
    global device_locator
    print(f'Version: {capsuleLib.get_version()}')
    device_locator = DeviceLocator('Logs', capsuleLib.get_lib())    # Create an object to search for devices
    device_locator.set_on_devices_list(on_device_list)      # Subscribe to receive the device list

    while not device_list_event_fired.is_awake():   # Try to find and connect to a device of the selected type until it succeeds
        device_locator.request_devices(DeviceType.Noise, 10)
        non_blocking_cond_wait(device_list_event_fired, 'device list to fire', 10)

    global device
    device.set_on_psd(on_psd)       # Subscribe to receive Power Spectral Density for each of the EEG channels
    device.connect(bipolarChannels=True)    # Connecting to the device in bipolar (True) or monopolar (False) mode
    non_blocking_cond_wait(device_connection_state_fired, 'device connected', 40)  
    channel_names_obj = device.get_channel_names()      # Get an object with the names of the electrodes
    print('EEG channel names:', [channel_names_obj.get_name_by_index(i) for i in range(len(channel_names_obj))])    # Output the electrode names to the console
    
    emotions = Emotions(device, capsuleLib.get_lib())   # Create an Emotions classifier
    emotions.set_on_states_update(on_emotions_states)   # Subscribe to receive data from the Emotions classifier

    cardio = Cardio(device, capsuleLib.get_lib())       # Create a Cardio classifier
    cardio.set_on_indexes_update(on_cardio_indexes)     # Subscribe to receive cardiometrics

    device.start()      # Start receiving data from the device
    print("Device start initialized")
    print('Mode: {mode}'.format(mode = device.get_mode().value))

    info = device.get_info()
    print('Got info from the device:')
    print('name: {n}'.format(n = info.get_name()))
    print('serial: {s}'.format(s = info.get_serial()))
    print('type: {t}'.format(t = info.get_type()))
    print('EEG sample rate: {sr}'.format(sr = device.get_eeg_sample_rate()))
    non_blocking_cond_wait(EventFiredState(), event_name='data collection', total_sleep_time=20)

    device.stop()  # Stop receiving data from the device
    device.disconnect()     # Send a command to disconnect from the device

if __name__ == "__main__":
    main()