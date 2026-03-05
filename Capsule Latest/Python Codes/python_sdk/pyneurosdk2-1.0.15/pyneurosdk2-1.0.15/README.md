# Python NeuroSDK 2

Welcome to the Python NeuroSDK 2. The Neurosdk library is designed to work with BrainBit, BrainBitBlack, Callibri and Kolibri devices. 

Supported Python 3.7 +

Supported platforms:
 - Windows 10 +
 - Astra Linux
 - Ubuntu 22.04
 - MacOS 10.14 +

## Documentation

- [Installing](#installing)
- [Description](#description)
- [Searching device](#searching-device)
- [Connection](#connection)
- [Parameters](#paramaters)
- [BrainBit sensor](#brainbit-brainbitblack-flex)
- [Callibri sensor](#callibri-kolibri)
- [BrainBit 2 sensor](#brainbit-2)
- [Clean up](#clean_up)

## Installing

```
pip install pyneurosdk2
```

### Linux

Supported:
 - Astra Linux
 - Ubuntu 22.04 

It is necessary to install NeuroSDK2 library before using it:

1. Download NeuroSDK2 `libneurosdk2.deb` package to your distribution from [GitHub](https://github.com/BrainbitLLC/linux_neurosdk2/tree/main/package)
2. Install package: 
```
sudo apt install ./libneurosdk2.deb
```

## Description

The package has the following structure:
 - neurosdk - the main package with the implementation of methods
 - sample - is into the neurosdk package, file `sample.py`
 - libs - also into neurosdk package, contain dll library files

The library provides three main modules:

- scanner - to search for devices

```python
from neurosdk.scanner import Scanner
```

- sensor - methods of interaction with the device

```python
from neurosdk.callibri_sensor import CallibriSensor
from neurosdk.brainbit_sensor import BrainBitSensor
from neurosdk.brainbit_2_sensor import BrainBit2Sensor
from neurosdk.brainbit_black_sensor import BrainBitBlackSensor
```

- types - implementation of all types of the library, you can either connect everything or only those necessary for a specific task

```python
from neurosdk.cmn_types import *
```

## Searching device

The `Scanner` class is used to search for a device. For a correct search, you must specify the list of device types. You can search for one or more device types at the same time. For example, to search for BrainBit and Callibri, you need to create a scanner as follows:

```python
scanner = Scanner([SensorFamily.LEBrainBit, SensorFamily.LEBrainBit2, SensorFamily.LECallibri])
```

Search start:

```python
scanner.start()
```

Stop search:

```python
scanner.stop()
```

All found devices can be obtained using the method:

```python
sensors = scanner.sensors()
```

During the search, an `sensorsChanged` callback will be called, which will display a list of found devices. If the device leaves the scanner's field of view for any reason, the device will disappear from the list after 12 seconds.

```python
def sensorFound(scanner, sensors):
   for i in range(len(sensors)):
       print('Sensor %s' % sensors[i])

scanner.sensorsChanged = sensorFound
```

The sensor's list will contain records of the SensorInfo type with fields:

- SensFamily: SensorFamily
- SensModel: int
- Name: str
- Address: str
- SerialNumber: str
- PairingRequired: bool
- RSSI: int

> Important!
> The serial number of the Callibri and Kolibri does not appear in the SensorInfo recieving during the search. To get this value, you need to connect to the device and request the serial number manually:
>
> ```python
> sn = sensor.serial_number
> ```


## Connection

Next, you can create any device from the list using the method:

```python
sensor = scanner.create_sensor(sensInfo)
```
When created, the device will connect automatically. This is a blocking function, so it is desirable to call it from an separate thread. Upon successful connection, a sensor instance will be returned. If unsuccessful, an exception is thrown. On subsequent connections and disconnections, a callback will be called indicating the state of the device.

To disconnect from the device, use the following method:

```python
sensor.disconnect()
```

To connect to a device created but not connected for any reason, the method:

```python
sensor.connect()
```

It is blocking too.

## Parameters

SDK allows you to get information about the connected device:

```python
print(sensor.sens_family)  # SensorFamily.LEBrainBit
print(sensor.features)  # [<SensorFeature.Signal: 0>, ...]
print(sensor.commands)  # [<SensorCommand.StartSignal: 0>,...]
print(sensor.parameters)
print(sensor.name)  # BrainBit
print(sensor.state)  # SensorState.StateInRange
print(sensor.address)  # AA:BB:CC:DD:EE:FF
print(sensor.serial_number)  # 123456
print(sensor.batt_power)  # 50
print(sensor.sampling_frequency)  # SensorSamplingFrequency.FrequencyHz250
print(sensor.gain)  # SensorGain.Gain6
print(sensor.data_offset)  # SensorDataOffset.DataOffset0
print(sensor.version)  # SensorVersion(FwMajor=50, FwMinor=0, FwPatch=0, HwMajor=1, HwMinor=0, HwPatch=0, ExtMajor=65)
```

>  You can distinguish BrainBit device from Flex by the firmware version number: if the `SensorVersion.FwMajor` is more than 100 - it's Flex, if it's less than BrainBit.

If you need to change any property, you first need to check if it is writable. This can be done by reading the list of device parameters, where each parameter will have an access level:

```
[ParameterInfo(Param=<SensorParameter.Offset: 8>, ParamAccess=<SensorParamAccess.Read: 0>),  
 ParameterInfo(Param=<SensorParameter.State: 1>,  ParamAccess=<SensorParamAccess.ReadNotify: 2>)
 ...]
```

And also check the support of certain modules:

```python
sensor.is_supported_feature(sensor_future)
sensor.is_supported_command(sensor_command)
sensor.is_supported_parameter(sensor_parameter)
```

## BrainBit, BrainBitBlack, Flex

### Gain

You can set gain parameter to BrainBit sensor:

```python
sensor.gain = SensorGain.Gain3
```

### Receiving signal

You can get the signal value using the callback:

```python
def on_brain_bit_signal_data_received(sensor, data):
    print(data)

sensor.signalDataReceived = on_brain_bit_signal_data_received

sensor.exec_command(SensorCommand.StartSignal)
sensor.exec_command(SensorCommand.StopSignal)
```

After you have finished working with the signal, you can unsubscribe from the callback as follows:

```python
sensor.signalDataReceived = None
```

It gives a list of packages. Each package contains:
- PackNum: int
- Marker: int
- O1: float
- O2: float
- T3: float
- T4: float

It is values from 4 channels in volts, a number for each packet and a marker if it was sent and this feature is supported by the device.

### Receiving resistance

To get resistance values:

```python
def on_brain_bit_resist_data_received(sensor, data):
    print(data)


sensor.resistDataReceived = on_brain_bit_resist_data_received

sensor.exec_command(SensorCommand.StartResist)
sensor.exec_command(SensorCommand.StopResist)
```

The callback returns one packet of samples, each packet contains the resistance values in volts:
- O1: float
- O2: float
- T3: float
- T4: float

After you have finished working with the resistance, you can unsubscribe from the callback as follows:

```python
sensor.resistDataReceived = None
```

> BrainBit cannot be in the resistance and signal readout mode at the same time, so you must first get the resistance values, but only after this signal, or vice versa. For example:
> ```python
> sensor.exec_command(SensorCommand.StartResist)
> sleep(10)
> sensor.exec_command(SensorCommand.StopResist)
> ...
> sensor.exec_command(SensorCommand.StartSignal)
> sleep(10)
> sensor.exec_command(SensorCommand.StopSignal)
> ```

## BrainBit 2

### Setup parameters

You can configure each channel and whole device settings by setting amplifier parameters.

```python
amp_param = sensor.amplifier_param  # current amplifier params
ch_count = sensor.channels_count    # channels count of devices
# setup Gain
amp_param.ChGain = [SensorGain.Gain6 for i in range(ch_count)]
# and other parameters
# amp_param.ChSignalMode = [BrainBit2ChannelMode.ChModeNormal for i in range(ch_count)]
# amp_param.ChResistUse = [True for i in range(ch_count)]
# amp_param.Current = GenCurrent.GenCurr6nA
sensor.amplifier_param = amp_param
```

Current - setting parameters of the probe current generator:
 - GenCurr0nA 
 - GenCurr6nA 
 - GenCurr12nA
 - GenCurr18nA
 - GenCurr24nA
 - GenCurr6uA 
 - GenCurr24uA
 - Unsupported

Signal modes:
 - Short - shorted input
 - Normal - bipolar input mode (used for EEG)

Resist use - doesn't used for current device version

Gain - gain of an ADC signal for each channel.

### Info about channels

The device can have 4 or 8 channels. To determine how many and which channels they are, you need to use the `supported_channels` property:

```python
supported_channels = sensor.supported_channels
```

`EEGChannelInfo` contains some info:
 - Id - `EEGChannelId` type - physical location of the channel. Possible values:
   - Unknown
   - O1 
   - P3 
   - C3 
   - F3 
   - Fp1
   - T5 
   - T3 
   - F7 
   - F8 
   - T4 
   - T6 
   - Fp2
   - F4 
   - C4 
   - P4 
   - O2 
   - D1 
   - D2 
   - OZ 
   - PZ 
   - CZ 
   - FZ 
   - FpZ
   - D3 

> IIn most cases, you will receive the values `O1`, `O2`, `T3`, `T4` or `Unknown`. `Unknown` means that the position of a specific electrode is free.

 - ChType - `EEGChannelType` type - type of channel, possible values `A1`, `A2`, `Differential` or `Referent`
 - Name - `String` type - channel name
 - Num - `number` type - channel number. By this number the channel will be located in the array of signal or resistance values

### AmpMode

This device can show it's current amplifier mode. It can be in the following states:

  - Invalid
  - PowerDown
  - Idle
  - Signal
  - Resist
  - SignalResist
  - Envelope

You can check amp. mode by two ways:

1. by callback:

```python
def on_amp_mode_changed(sensor, mode):
    print('Amp mode: {0}'.format(mode))
    
    
sensor.sensorAmpModeChanged = on_amp_mode_changed
```

2. get value at any time:

```python
mode  = sensor.amp_mode
```

It is very important parameter for BrainBit2 device because you can set amplifier parameters only if device into `PowerDown` or `Idle` mode.

### Receiving signal

To receive signal data, you need to subscribe to the corresponding callback. The values come in volts. In order for the device to start transmitting data, you need to start a signal using the `execute` command. This method is also recommended to be run in an separate thread.

```python
def on_signal_data_received(sensor, data):
    print(data)

sensor.signalDataReceived = on_signal_data_received
```

After you have finished working with the signal, you can unsubscribe from the callback as follows:

```python
sensor.signalDataReceived = None
```

It gives a list of packages `SignalChannelsData`. Each package contains:
- PackNum: int - number for each packet
- Marker: int - marker of sample
- Samples: [float] - array of samples in V. Each sample number into array consistent with `Num` value of `EEGChannelInfo` from `supported_channels` property.

### Receiving resistance

To get resistance values:

```python
def on_brain_bit_2_resist_data_received(sensor, data):
    print(data)


sensor.resistDataReceived = on_brain_bit_2_resist_data_received

sensor.exec_command(SensorCommand.StartResist)
sensor.exec_command(SensorCommand.StopResist)
```

You get resistance values structure of samples (`ResistRefChannelsData`) for each channel:
 - PackNum: int - number for each packet
 - Samples: [float] - array of values in Ohm. Each sample number into array consistent with `Num` value of `EEGChannelInfo` from `supported_channels` property.
 - Referents: [float] - array of values for referents channels. For BrainBit2 sensor is empty now.

After you have finished working with the resistance, you can unsubscribe from the callback as follows:

```python
sensor.resistDataReceived = None
```

## Callibri, Kolibri

### Receiving signal

You can get the signal value using the callback:

```python
def on_callibri_signal_data_received(sensor, data):
   print(data)

sensor.signalDataReceived = on_callibri_signal_data_received
```

After you have finished working with the signal, you can unsubscribe from the callback as follows:

```python
sensor.signalDataReceived = None
```

It gives a list of packages. Each package contains:
 - PackNum: int
 - Samples: [float]

It is values in volts and a number for each packet.

### Electrodes connection

Electrode placement check is available for Callibri and Kolibri devices. This data shows whether the electrodes are attached to the skin.

```python
def onCallibriElectrodeStateChanged(sensor, data):
   print(data)

sensor.electrodeStateChanged = onCallibriElectrodeStateChanged
```

For unsubscribe from callback:

```python
sensor.electrodeStateChanged = None
```

Electrodes state can be one of values of enum:
- ElStNormal = 0
- ElStHighResistance = 1
- ElStDetached = 2

To get the state of the electrodes, you need to start a signal from the device.You can receive electrode and signal values at the same time.

## Clean up

After you finish working with the device, you need to clean up the resources used. This happens in the destructor of the scanner and sensor, so if they were not called by the system, you must call them manually.

```python
del sensor
del scanner
```
