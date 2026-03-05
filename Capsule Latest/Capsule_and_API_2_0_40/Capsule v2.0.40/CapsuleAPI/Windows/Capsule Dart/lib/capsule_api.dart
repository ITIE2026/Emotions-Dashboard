// ignore_for_file: constant_identifier_names, non_constant_identifier_names

import 'package:ffi/ffi.dart';
import 'dart:ffi';
import 'dart:io';

class Resistance {
  String channelName;
  double value;

  Resistance._(this.channelName, this.value);
}

class Point3d {
  double x, y, z;

  Point3d._(_NativePoint3d nativePoint)
      : x = nativePoint.x,
        y = nativePoint.y,
        z = nativePoint.z;
}

class MEMSSample {
  Point3d accelerometer;
  Point3d gyroscope;
  int timestampMilli;

  MEMSSample._(this.accelerometer, this.gyroscope, this.timestampMilli);
}

class PPGSample {
  double value;
  int timestampMilli;

  PPGSample._(this.value, this.timestampMilli);
}

class EEGSample {
  List<double> channels;
  List<double> processedChannels;
  int timestampMilli;

  EEGSample._(this.channels, this.processedChannels, this.timestampMilli);
}

class EEGArtifact {
  int artifactByChannel;
  double eegQuality;

  EEGArtifact._(this.artifactByChannel, this.eegQuality);
}

class EEGArtifacts {
  int timestampMilli;
  List<EEGArtifact> artifacts;
  EEGArtifacts._(this.timestampMilli, this.artifacts);
}

class PSDSample {
  double frequency;
  List<double> spectrum;
  PSDSample._(this.frequency, this.spectrum);
}

class BandFrequencies {
  double lower;
  double upper;
  BandFrequencies(this.lower, this.upper);
}

class PSDData {
  List<PSDSample> spectrum;
  int timestampMilli;
  Map<PSDBand, BandFrequencies> bands;
  BandFrequencies? individualAlpha;
  BandFrequencies? individualBeta;
  PSDData._(this.spectrum, this.timestampMilli, this.bands,
      this.individualAlpha, this.individualBeta);
}

class DeviceInfo {
  String id;
  String name;
  DeviceType deviceType;

  DeviceInfo._(this.id, this.name, this.deviceType);
}

enum ErrorCode {
  ok,
  failedToConnect,
  failedToInitConnection,
  failedToInitialize,
  deviceError,
  individualNFBNotCalibrated,
  notReceived,
  nullPointer,
  moduleAlreadyExists,
  moduleIsNotSupported,
  failedToSendData,
  indexOutOfRange,
  emptyCollection,
  notFound,
  sizeMismatch,
  unknownEnum,
  unknown // = 255
}

enum DisconnectReason { userRequested, destruction, fatalError }

enum DeviceType {
  Band,
  Buds,
  Headphones,
  Impulse,
  Any,
  BrainBit,
  SinWave,
  Noise
}

enum DeviceMode {
  resistance,
  unspecified,
  signal,
  startMEMS,
  stopMEMS,
  startPPG,
  stopPPG,
  signalAndResistance
}

enum DeviceConnectionState { disconnected, connected, unsupportedConnection }

enum DeviceStatus {
  invalid,
  powerDown,
  idle,
  signal,
  resistance,
  signalAndResistance,
  envelope
}

enum UserActivity {
  activity1,
  activity2,
  activity3,
  activity4,
  activity5,
  none
}

enum IndividualNFBCalibrationStage { stage1, stage2, stage3, stage4 }

Map<Pointer<Void>, Object> _obj = {};

T _getObj<T>(Pointer<Void> handle) {
  return _obj[handle] as T;
}

typedef _Callback<T> = T Function(Pointer<_NativeError> errorPtr);

ErrorCode _fromNative(int code) {
  if (code == 255) {
    return ErrorCode.unknown;
  }
  return ErrorCode.values[code];
}

String _arrayToString(Array<Char> array) {
  final stringList = <int>[];
  var i = 0;
  while (array[i] != 0) {
    stringList.add(array[i]);
    i++;
  }
  return String.fromCharCodes(stringList);
}

T _checkAndFreeNativeError<T>(_Callback<T> callable) {
  final error = malloc<_NativeError>();
  final T result = callable(error);
  String? errorStr;
  if (!error.ref.success) {
    errorStr =
        "${_arrayToString(error.ref.message)} - ${_fromNative(error.ref.code)}";
  }
  malloc.free(error);
  if (errorStr != null) {
    throw Exception(errorStr);
  }
  return result;
}

enum DeviceLocatorFailReason { ok, bluetoothDisabled, unknown }

class _NativeOwner {
  Pointer<Void> _handle = nullptr;

  bool get empty => _handle == nullptr;

  void _checkEmpty() {
    if (empty) throw Exception("Empty handle");
  }

  void destroy() {
    _obj.remove(_handle);
    _handle = nullptr;
  }
}

class _NativePoint3d extends Struct {
  @Float()
  external double x, y, z;
}

enum LogLevel { trace, debug, info, warn, err, critical, off }

class Capsule {
  static LogLevel get logLevel => LogLevel.values[_CapsuleAPI._getLogLevel()];
  static set logLevel(LogLevel logLevel) =>
      _CapsuleAPI._setLogLevel(logLevel.index);

  static String get version => _CapsuleAPI._getVersionString().toDartString();
}

class DeviceLocator extends _NativeOwner {
  DeviceLocator() {
    _checkSizes();
    _CapsuleAPI._setSingleThreaded(true);
    _handle = _checkAndFreeNativeError(
        (errorPtr) => _CapsuleAPI._createDeviceLocator(errorPtr));
    _init();
  }

  DeviceLocator.withLogDir(String logDir) {
    _checkSizes();
    _CapsuleAPI._setSingleThreaded(true);
    _handle = _checkAndFreeNativeError((errorPtr) =>
        _CapsuleAPI._createDeviceLocatorWithLogDirectory(
            logDir.toNativeUtf8(), errorPtr));
    _init();
  }

  void _init() {
    if (_handle == nullptr) {
      throw Exception("Cannot create DeviceLocator");
    }
    _obj[_handle] = this;
    _CapsuleAPI._setDeviceLocatorDevicesEvent(
        _handle, Pointer.fromFunction<_DeviceListHandler>(_devicesCallback));
  }

  void update() {
    _checkEmpty();
    _CapsuleAPI._update(_handle);
  }

  @override
  void destroy() {
    _checkEmpty();
    _CapsuleAPI._destroyDeviceLocator(_handle);
    super.destroy();
  }

  void requestDevices(DeviceType deviceType, int searchDuration) {
    _checkEmpty();
    _checkAndFreeNativeError((error) => {
          _CapsuleAPI._requestDevices(
              _handle, _toInt(deviceType), searchDuration, error)
        });
  }

  set devicesHandler(
      Function(List<DeviceInfo>, DeviceLocatorFailReason) handler) {
    _devicesHandler = handler;
  }

  Device lockDevice(String id) {
    _checkEmpty();
    final deviceHandle = _checkAndFreeNativeError(
        (error) => _CapsuleAPI._lockDevice(_handle, id.toNativeUtf8(), error));
    if (deviceHandle == nullptr) {
      throw Exception("Failed to lock device");
    }
    return Device._(deviceHandle);
  }

  Function(List<DeviceInfo>, DeviceLocatorFailReason) _devicesHandler =
      (devices, failReason) {};

  static List<DeviceInfo> _getDevices(Pointer<Void> devicesPtr) {
    return List.generate(
        _checkAndFreeNativeError(
            (errorPtr) => _CapsuleAPI._devicesGetCount(devicesPtr, errorPtr)),
        (index) {
      final devicePtr = _checkAndFreeNativeError((errorPtr) =>
          _CapsuleAPI._devicesGetDevice(devicesPtr, index, errorPtr));
      return _getDeviceInfo(devicePtr);
    });
  }

  static DeviceType _fromInt(int deviceType) {
    switch (deviceType) {
      case 100:
        return DeviceType.SinWave;
      case 101:
        return DeviceType.Noise;
      case 6:
        return DeviceType.BrainBit;
      default:
        return DeviceType.values[deviceType];
    }
  }

  static int _toInt(DeviceType deviceType) {
    switch (deviceType) {
      case DeviceType.SinWave:
        return 100;
      case DeviceType.Noise:
        return 101;
      case DeviceType.BrainBit:
        return 6;
      default:
        return deviceType.index;
    }
  }

  static DeviceInfo _getDeviceInfo(Pointer<Void> devicePtr) {
    final deviceId = _CapsuleAPI._deviceGetID(devicePtr).toDartString();
    final deviceName = _CapsuleAPI._deviceGetName(devicePtr).toDartString();
    final int devType = _CapsuleAPI._deviceGetType(devicePtr);
    final deviceType = _fromInt(devType);
    return DeviceInfo._(deviceId, deviceName, deviceType);
  }

  static void _devicesCallback(
      Pointer<Void> handle, Pointer<Void> devicesPtr, int failReason) {
    final locator = _getObj<DeviceLocator>(handle);
    locator._devicesHandler(
        _getDevices(devicesPtr), DeviceLocatorFailReason.values[failReason]);
  }
}

enum PSDBand { delta, theta, alpha, smr, beta }

class Device extends _NativeOwner {
  final List<Pointer<Void>> _classifiers = [];

  Device._(Pointer<Void> handle) {
    _handle = handle;
    _CapsuleAPI._setDeviceConnectionEvent(_handle,
        Pointer.fromFunction<_EnumHandler>(_deviceConnectionStateCallback));
    _CapsuleAPI._setResistancesEventHandler(_handle,
        Pointer.fromFunction<_PointerHandler>(_deviceResistancesCallback));
    _CapsuleAPI._setBatteryEventHandler(
        _handle, Pointer.fromFunction<_CharHandler>(_deviceBatteryCallback));
    _CapsuleAPI._setDeviceModeEventHandler(
        _handle, Pointer.fromFunction<_EnumHandler>(_deviceModeCallback));
    _CapsuleAPI._setDeviceErrorEventHandler(
        _handle, Pointer.fromFunction<_StringHandler>(_deviceErrorCallback));

    _CapsuleAPI._setDeviceEEGEventHandler(
        _handle, Pointer.fromFunction<_PointerHandler>(_deviceEEGDataCallback));
    _CapsuleAPI._setDevicePSDEventHandler(
        _handle, Pointer.fromFunction<_PointerHandler>(_devicePSDDataCallback));
    _CapsuleAPI._setDeviceEEGArtifactsEventHandler(_handle,
        Pointer.fromFunction<_PointerHandler>(_deviceEEGArtifactsCallback));
    _obj[_handle] = this;
  }

  set connectionStateHandler(Function(DeviceConnectionState) handler) {
    _deviceConnectionStateHandler = handler;
  }

  set resistancesHandler(Function(List<Resistance>) handler) {
    _deviceResistancesHandler = handler;
  }

  set batteryHandler(Function(int) handler) {
    _deviceBatteryHandler = handler;
  }

  set deviceModeHandler(Function(DeviceMode) handler) {
    _deviceModeHandler = handler;
  }

  set errorHandler(Function(String) handler) {
    _errorHandler = handler;
  }

  set eegDataHandler(Function(List<EEGSample>) handler) {
    _eegDataHandler = handler;
  }

  set eegArtifactsHandler(Function(EEGArtifacts) handler) {
    _eegArtifactsHandler = handler;
  }

  set psdDataHandler(Function(PSDData) handler) {
    _psdDataHandler = handler;
  }

  @override
  void destroy() {
    _checkEmpty();
    _CapsuleAPI._releaseDevice(_handle);
    for (final classifierHandle in _classifiers) {
      _obj.remove(classifierHandle);
    }
    super.destroy();
  }

  void connect(bool bipolarChannels) {
    _checkEmpty();
    _checkAndFreeNativeError(
        (error) => _CapsuleAPI._deviceConnect(_handle, bipolarChannels, error));
  }

  void disconnect() {
    _checkEmpty();
    _checkAndFreeNativeError(
        (error) => _CapsuleAPI._deviceDisconnect(_handle, error));
  }

  void start() {
    _checkEmpty();
    _checkAndFreeNativeError(
        (error) => _CapsuleAPI._deviceStart(_handle, error));
  }

  void stop() {
    _checkEmpty();
    _checkAndFreeNativeError(
        (error) => _CapsuleAPI._deviceStop(_handle, error));
  }

  int get batteryCharge {
    _checkEmpty();
    return _checkAndFreeNativeError(
        (error) => _CapsuleAPI._batteryCharge(_handle, error));
  }

  DeviceMode get deviceMode {
    _checkEmpty();
    return DeviceMode.values[_CapsuleAPI._deviceMode(_handle)];
  }

  double get eegSampleRate {
    _checkEmpty();
    return _checkAndFreeNativeError(
        (errorPtr) => _CapsuleAPI._deviceGetEEGSampleRate(_handle, errorPtr));
  }

  double get ppgSampleRate {
    _checkEmpty();
    return _checkAndFreeNativeError(
        (errorPtr) => _CapsuleAPI._deviceGetPPGSampleRate(_handle, errorPtr));
  }

  double get memsSampleRate {
    _checkEmpty();
    return _checkAndFreeNativeError(
        (errorPtr) => _CapsuleAPI._deviceGetMEMSSampleRate(_handle, errorPtr));
  }

  int get ppgRedAmplitude {
    _checkEmpty();
    return _checkAndFreeNativeError(
        (errorPtr) => _CapsuleAPI._deviceGetPPGRedAmplitude(_handle, errorPtr));
  }

  int get ppgIrAmplitude {
    _checkEmpty();
    return _checkAndFreeNativeError(
        (errorPtr) => _CapsuleAPI._deviceGetPPGIrAmplitude(_handle, errorPtr));
  }

  bool get connected {
    _checkEmpty();
    return _checkAndFreeNativeError(
            (error) => _CapsuleAPI._isDeviceConnected(_handle, error)) !=
        0;
  }

  DeviceInfo get info {
    _checkEmpty();
    return _checkAndFreeNativeError((error) => DeviceLocator._getDeviceInfo(
        _CapsuleAPI._deviceGetInfo(_handle, error)));
  }

  List<String> get channelNames {
    _checkEmpty();
    final channelNamesPtr = _checkAndFreeNativeError(
        (errorPtr) => _CapsuleAPI._deviceGetChannelNames(_handle, errorPtr));
    return List.generate(
        _checkAndFreeNativeError((errorPtr) =>
            _CapsuleAPI._deviceChannelNamesGetCount(channelNamesPtr, errorPtr)),
        (index) {
      final channelNamePtr = _checkAndFreeNativeError((errorPtr) =>
          _CapsuleAPI._deviceChannelNamesGetNameByIndex(
              channelNamesPtr, index, errorPtr));
      return channelNamePtr.toDartString();
    });
  }

  Function(DeviceConnectionState) _deviceConnectionStateHandler =
      (connected) {};
  Function(List<Resistance>) _deviceResistancesHandler = (resistances) {};
  Function(int) _deviceBatteryHandler = (battery) {};
  Function(DeviceMode) _deviceModeHandler = (mode) {};
  Function(List<EEGSample>) _eegDataHandler = (eeg) {};
  Function(EEGArtifacts) _eegArtifactsHandler = (artifacts) {};
  Function(PSDData) _psdDataHandler = (eeg) {};
  Function(String) _errorHandler = (error) {};

  static void _deviceConnectionStateCallback(
      Pointer<Void> handle, int connected) {
    final device = _getObj<Device>(handle);
    device
        ._deviceConnectionStateHandler(DeviceConnectionState.values[connected]);
  }

  static void _deviceResistancesCallback(
      Pointer<Void> handle, Pointer<Void> resistancesPtr) {
    final device = _getObj<Device>(handle);
    device._deviceResistancesHandler(_getResistances(resistancesPtr));
  }

  static void _deviceBatteryCallback(Pointer<Void> handle, int batteryCharge) {
    final device = _getObj<Device>(handle);
    device._deviceBatteryHandler(batteryCharge);
  }

  static void _deviceModeCallback(Pointer<Void> handle, int deviceMode) {
    final device = _getObj<Device>(handle);
    device._deviceModeHandler(DeviceMode.values[deviceMode]);
  }

  static void _deviceEEGDataCallback(
      Pointer<Void> handle, Pointer<Void> eegDataPtr) {
    final device = _getObj<Device>(handle);
    device._eegDataHandler(_getEEG(eegDataPtr));
  }

  static void _devicePSDDataCallback(
      Pointer<Void> handle, Pointer<Void> psdDataPtr) {
    final device = _getObj<Device>(handle);
    device._psdDataHandler(_getPSD(psdDataPtr));
  }

  static void _deviceEEGArtifactsCallback(
      Pointer<Void> handle, Pointer<Void> eegArtifactsDataPtr) {
    final device = _getObj<Device>(handle);
    device._eegArtifactsHandler(_getEEGArtifacts(eegArtifactsDataPtr));
  }

  static void _deviceErrorCallback(
      Pointer<Void> handle, Pointer<Utf8> errorPtr) {
    final device = _getObj<Device>(handle);
    device._errorHandler(errorPtr.toDartString());
  }

  static List<Resistance> _getResistances(Pointer<Void> resistancesPtr) {
    return List.generate(_CapsuleAPI._resistancesGetCount(resistancesPtr),
        (index) {
      final channelName =
          _CapsuleAPI._resistancesGetChannelName(resistancesPtr, index)
              .toDartString();
      return Resistance._(channelName,
          _CapsuleAPI._resistancesGetResistance(resistancesPtr, index));
    });
  }

  static List<EEGSample> _getEEG(Pointer<Void> eegPtr) {
    return _checkAndFreeNativeError((errorPtr) {
      final channelsCount =
          _CapsuleAPI._eegTimedDataGetChannelsCount(eegPtr, errorPtr);
      return List.generate(
          _CapsuleAPI._eegTimedDataGetSamplesCount(eegPtr, errorPtr),
          (sampleIndex) {
        final rawSamples = List.generate(
            channelsCount,
            (channelIndex) => _CapsuleAPI._eegTimedDataGetRawValue(
                eegPtr, channelIndex, sampleIndex, errorPtr));
        final processedSamples = List.generate(
            channelsCount,
            (channelIndex) => _CapsuleAPI._eegTimedDataGetProcessedValue(
                eegPtr, channelIndex, sampleIndex, errorPtr));
        return EEGSample._(
            rawSamples,
            processedSamples,
            _CapsuleAPI._eegTimedDataGetTimestampMilli(
                eegPtr, sampleIndex, errorPtr));
      });
    });
  }

  static EEGArtifacts _getEEGArtifacts(Pointer<Void> eegArtifactsPtr) {
    return _checkAndFreeNativeError((errorPtr) {
      final channelsCount =
          _CapsuleAPI._eegArtifactsGetChannelsCount(eegArtifactsPtr, errorPtr);
      return EEGArtifacts._(
          _CapsuleAPI._eegArtifactsGetTimestampMilli(eegArtifactsPtr, errorPtr),
          List.generate(
              channelsCount,
              (index) => EEGArtifact._(
                  _CapsuleAPI._eegArtifactsGetArtifactByChannel(
                      eegArtifactsPtr, index, errorPtr),
                  _CapsuleAPI._eegArtifactsGetEEGQuality(
                      eegArtifactsPtr, index, errorPtr))));
    });
  }

  static PSDData _getPSD(Pointer<Void> psdDataPtr) {
    return _checkAndFreeNativeError((errorPtr) {
      final frequenciesCount =
          _CapsuleAPI._psdDataGetFrequenciesCount(psdDataPtr, errorPtr);
      return PSDData._(
          List.generate(frequenciesCount, (frequencyIndex) {
            return PSDSample._(
                _CapsuleAPI._psdDataGetFrequency(
                    psdDataPtr, frequencyIndex, errorPtr),
                List.generate(
                    _CapsuleAPI._psdDataGetChannelsCount(psdDataPtr, errorPtr),
                    (channelIndex) {
                  return _CapsuleAPI._psdDataGetPSD(
                      psdDataPtr, channelIndex, frequencyIndex, errorPtr);
                }));
          }),
          _CapsuleAPI._psdDataGetTimestampMilli(psdDataPtr, errorPtr),
          _getPSDBands(psdDataPtr, errorPtr),
          _getIndividualAlpha(psdDataPtr, errorPtr),
          _getIndividualBeta(psdDataPtr, errorPtr));
    });
  }

  static Map<PSDBand, BandFrequencies> _getPSDBands(
      Pointer<Void> psdDataPtr, Pointer<_NativeError> errorPtr) {
    Map<PSDBand, BandFrequencies> bands = {};
    for (final band in PSDBand.values) {
      final lower =
          _CapsuleAPI._psdDataGetBandLower(psdDataPtr, band.index, errorPtr);
      final upper =
          _CapsuleAPI._psdDataGetBandUpper(psdDataPtr, band.index, errorPtr);
      bands[band] = BandFrequencies(lower, upper);
    }
    return bands;
  }

  static BandFrequencies? _getIndividualAlpha(
      Pointer<Void> psdDataPtr, Pointer<_NativeError> errorPtr) {
    final hasIndividualAlpha =
        _CapsuleAPI._psdDataHasIndividualAlpha(psdDataPtr, errorPtr);
    if (!hasIndividualAlpha) return null;

    final lower =
        _CapsuleAPI._psdDataGetIndividualAlphaLower(psdDataPtr, errorPtr);
    final upper =
        _CapsuleAPI._psdDataGetIndividualAlphaUpper(psdDataPtr, errorPtr);
    return BandFrequencies(lower, upper);
  }

  static BandFrequencies? _getIndividualBeta(
      Pointer<Void> psdDataPtr, Pointer<_NativeError> errorPtr) {
    final hasIndividualBeta =
        _CapsuleAPI._psdDataHasIndividualBeta(psdDataPtr, errorPtr);
    if (!hasIndividualBeta) return null;

    final lower =
        _CapsuleAPI._psdDataGetIndividualBetaLower(psdDataPtr, errorPtr);
    final upper =
        _CapsuleAPI._psdDataGetIndividualBetaUpper(psdDataPtr, errorPtr);
    return BandFrequencies(lower, upper);
  }
}

enum IndividualNFBCalibrationFailReason {
  none,
  tooManyArtifacts,
  peakIsABorder
}

class IndividualNFBInfo {
  int timestampMilli;
  IndividualNFBCalibrationFailReason failReason;
  double individualFrequency;
  double individualPeakFrequency,
      individualPeakFrequencyPower,
      individualPeakFrequencySuppression;
  double individualBandwidth;
  double individualNormalizedPower;
  double lowerFrequency, upperFrequency;

  IndividualNFBInfo._(_IndividualNFBInfo nativeInfo)
      : timestampMilli = nativeInfo.timestampMilli,
        failReason =
            IndividualNFBCalibrationFailReason.values[nativeInfo.failReason],
        individualFrequency = nativeInfo.individualFrequency,
        individualPeakFrequency = nativeInfo.individualPeakFrequency,
        individualPeakFrequencyPower = nativeInfo.individualPeakFrequencyPower,
        individualPeakFrequencySuppression =
            nativeInfo.individualPeakFrequencySuppression,
        individualBandwidth = nativeInfo.individualBandwidth,
        individualNormalizedPower = nativeInfo.individualNormalizedPower,
        lowerFrequency = nativeInfo.lowerFrequency,
        upperFrequency = nativeInfo.upperFrequency;

  void _toNative(Pointer<_IndividualNFBInfo> native) {
    final ref = native.ref;
    ref.timestampMilli = timestampMilli;
    ref.failReason = failReason.index;
    ref.individualFrequency = individualFrequency;
    ref.individualPeakFrequency = individualPeakFrequency;
    ref.individualPeakFrequencyPower = individualPeakFrequencyPower;
    ref.individualPeakFrequencySuppression = individualPeakFrequencySuppression;
    ref.individualBandwidth = individualBandwidth;
    ref.individualNormalizedPower = individualNormalizedPower;
    ref.lowerFrequency = lowerFrequency;
    ref.upperFrequency = upperFrequency;
  }
}

class _IndividualNFBInfo extends Struct {
  @Int64()
  external int timestampMilli;
  @Int32()
  external int failReason;
  @Float()
  external double individualFrequency;
  @Float()
  external double individualPeakFrequency,
      individualPeakFrequencyPower,
      individualPeakFrequencySuppression;
  @Float()
  external double individualBandwidth;
  @Float()
  external double individualNormalizedPower;
  @Float()
  external double lowerFrequency, upperFrequency;
}

class CardioData {
  int timestampMilli;
  double heartRate, stressIndex, kaplanIndex;
  bool hasArtifacts, skinContact, motionArtifacts, metricsAvailable;

  CardioData._(_NativeCardioData nativeData)
      : timestampMilli = nativeData.timestampMilli,
        heartRate = nativeData.heartRate,
        stressIndex = nativeData.stressIndex,
        kaplanIndex = nativeData.kaplanIndex,
        hasArtifacts = nativeData.hasArtifacts,
        skinContact = nativeData.skinContact,
        motionArtifacts = nativeData.motionArtifacts,
        metricsAvailable = nativeData.metricsAvailable;
}

class _NativeCardioData extends Struct {
  @Int64()
  external int timestampMilli;
  @Float()
  external double heartRate, stressIndex, kaplanIndex;
  @Bool()
  external bool hasArtifacts, skinContact, motionArtifacts, metricsAvailable;
}

class Cardio extends _NativeOwner {
  Cardio(Device device) {
    if (device.empty) throw Exception("Empty device handle");
    _handle = _checkAndFreeNativeError((errorPtr) {
      return _CapsuleAPI._cardioCreate(device._handle, errorPtr);
    });
    _init(device);
  }

  Cardio.calibrated(Device device, NFBCalibrator calibrator) {
    if (device.empty) throw Exception("Empty device handle");
    _handle = _checkAndFreeNativeError((errorPtr) {
      return _CapsuleAPI._cardioCreateCalibrated(
          device._handle, calibrator._handle, errorPtr);
    });
    _init(device);
  }

  void _init(Device device) {
    if (_handle == nullptr) {
      throw Exception("Failed to create Cardio classifier");
    }
    _obj[_handle] = this;
    device._classifiers.add(_handle);
    _checkAndFreeNativeError((errorPtr) {
      _CapsuleAPI._setCardioCalibratedEventHandler(_handle,
          Pointer.fromFunction<_Handler>(_cardioCalibratedCallback), errorPtr);
      _CapsuleAPI._setCardioIndexesEventHandler(
          _handle,
          Pointer.fromFunction<_CardioDataHandler>(_cardioIndexesCallback),
          errorPtr);
    });
  }

  Function() _calibratedHandler = () {};
  set calibratedHandler(Function() value) {
    _calibratedHandler = value;
  }

  Function(List<PPGSample>) _ppgDataHandler = (ppg) {};
  set ppgDataHandler(Function(List<PPGSample>) handler) {
    _ppgDataHandler = handler;

    _checkAndFreeNativeError((errorPtr) {
      _CapsuleAPI._setCardioPPGDataEventHandler(
          _handle,
          Pointer.fromFunction<_PointerHandler>(_cardioPPGDataCallback),
          errorPtr);
    });
  }

  static void _cardioPPGDataCallback(
      Pointer<Void> handle, Pointer<Void> ppgDataPtr) {
    final cardio = _getObj<Cardio>(handle);
    cardio._ppgDataHandler(_getPPG(ppgDataPtr));
  }

  static void _cardioCalibratedCallback(Pointer<Void> handle) {
    var cardio = _obj[handle] as Cardio;

    cardio._calibratedHandler();
  }

  Function(CardioData) _indexesHandler = (data) {};
  set indexesHandler(Function(CardioData) value) {
    _indexesHandler = value;
  }

  static void _cardioIndexesCallback(
      Pointer<Void> handle, Pointer<_NativeCardioData> cardioData) {
    var cardio = _obj[handle] as Cardio;

    cardio._indexesHandler(CardioData._(cardioData.ref));
  }

  static List<PPGSample> _getPPG(Pointer<Void> ppgPtr) {
    return List.generate(_CapsuleAPI._ppgGetCount(ppgPtr), (index) {
      return PPGSample._(_CapsuleAPI._ppgGetValue(ppgPtr, index),
          _CapsuleAPI._ppgGetTimestampMilli(ppgPtr, index));
    });
  }
}

class MEMS extends _NativeOwner {
  MEMS(Device device) {
    if (device.empty) throw Exception("Empty device handle");
    _handle = _checkAndFreeNativeError((errorPtr) {
      return _CapsuleAPI._memsCreate(device._handle, errorPtr);
    });
    _init(device);
  }

  MEMS.calibrated(Device device, NFBCalibrator calibrator) {
    if (device.empty) throw Exception("Empty device handle");
    _handle = _checkAndFreeNativeError((errorPtr) {
      return _CapsuleAPI._memsCreateCalibrated(
          device._handle, calibrator._handle, errorPtr);
    });
    _init(device);
  }

  void _init(Device device) {
    _obj[_handle] = this;
    device._classifiers.add(_handle);
  }

  Function(List<MEMSSample>) _memsDataHandler = (mems) {};
  set memsDataHandler(Function(List<MEMSSample>) handler) {
    _memsDataHandler = handler;

    _checkAndFreeNativeError((errorPtr) {
      _CapsuleAPI._setMEMSDataEventHandler(
          _handle,
          Pointer.fromFunction<_PointerHandler>(_memsMEMSDataCallback),
          errorPtr);
    });
  }

  static void _memsMEMSDataCallback(
      Pointer<Void> handle, Pointer<Void> memsDataPtr) {
    final mems = _getObj<MEMS>(handle);
    mems._memsDataHandler(_getMEMS(memsDataPtr));
  }

  static List<MEMSSample> _getMEMS(Pointer<Void> memsPtr) {
    return List.generate(_CapsuleAPI._memsGetCount(memsPtr), (index) {
      return MEMSSample._(
          Point3d._(_CapsuleAPI._memsGetAccelerometer(memsPtr, index)),
          Point3d._(_CapsuleAPI._memsGetGyroscope(memsPtr, index)),
          _CapsuleAPI._memsGetTimestampMilli(memsPtr, index));
    });
  }
}

enum NFBCallResult {
  /// < Call has finished successfully.
  success,

  /// < Failed to send data, session might not be active.
  failedToSendData
}

enum NFBState { undefined, relaxation, concentration }

class Productivity extends _NativeOwner {
  Productivity(Device device) {
    if (device.empty) throw Exception("Empty device handle");

    _handle = _checkAndFreeNativeError((errorPtr) {
      return _CapsuleAPI._productivityCreate(device._handle, errorPtr);
    });
    _init(device);
  }

  Productivity.withIndividualData(
      Device device, IndividualNFBInfo individualData) {
    if (device.empty) throw Exception("Empty device handle");

    _handle = _checkAndFreeNativeError((errorPtr) {
      final nativeInfo = malloc<_IndividualNFBInfo>();
      individualData._toNative(nativeInfo);
      final h = _CapsuleAPI._productivityCreateWithIndividualData(
          device._handle, nativeInfo, errorPtr);
      malloc.free(nativeInfo);
      return h;
    });
    _init(device);
  }

  void _init(Device device) {
    if (_handle == nullptr) {
      throw Exception("Failed to create Producitity");
    }
    _obj[_handle] = this;
    device._classifiers.add(_handle);
    _CapsuleAPI._setProductivityCalibrationProgressHandler(_handle,
        Pointer.fromFunction<_FloatHandler>(_calibrationProgressCallback));
    _CapsuleAPI._setProductivityIndividualNFBUpdateHandler(
        _handle, Pointer.fromFunction<_Handler>(_individualNFBUpdateCallback));
    _CapsuleAPI._setProductivityBaselinesHandler(
        _handle,
        Pointer.fromFunction<_ProductivityBaselinesHandler>(
            _baselinesCallback));
    _CapsuleAPI._setProductivityMetricsHandler(_handle,
        Pointer.fromFunction<_ProductivityMetricsHandler>(_metricsCallback));
    _CapsuleAPI._setProductivityIndexesHandler(_handle,
        Pointer.fromFunction<_ProductivityIndexesHandler>(_indexesCallback));
  }

  void importBaselines(ProductivityBaselines baselines) {
    _checkAndFreeNativeError((errorPtr) {
      final nativeBaselines = malloc<_NativeProductivityBaselines>();
      baselines._toNative(nativeBaselines);
      _CapsuleAPI._productivityImportBaselines(
          _handle, nativeBaselines, errorPtr);
      malloc.free(nativeBaselines);
    });
  }

  void resetAccumulatedFatigue() {
    _checkAndFreeNativeError((errorPtr) {
      _CapsuleAPI._productivityResetAccumulatedFatigue(_handle, errorPtr);
    });
  }

  void startBaselineCalibration() {
    _CapsuleAPI._productivityStartBaselineCalibration(_handle);
  }

  Function(double) _calibrationProgressHandler = (progress) {};
  Function() _individualNFBUpdateHandler = () {};
  Function(ProductivityBaselines) _baselinesHandler = (baselines) {};
  Function(ProductivityMetrics) _metricsHandler = (metrics) {};
  Function(ProductivityIndexes) _indexesHandler = (indexes) {};

  set calibrationProgressHandler(Function(double) handler) {
    _calibrationProgressHandler = handler;
  }

  set individualNFBUpdateHandler(Function() handler) {
    _individualNFBUpdateHandler = handler;
  }

  set baselinesHandler(Function(ProductivityBaselines) handler) {
    _baselinesHandler = handler;
  }

  set metricsHandler(Function(ProductivityMetrics) handler) {
    _metricsHandler = handler;
  }

  set indexesHandler(Function(ProductivityIndexes) handler) {
    _indexesHandler = handler;
  }

  static void _calibrationProgressCallback(
      Pointer<Void> handle, double metric) {
    final productivity = _obj[handle] as Productivity;

    productivity._calibrationProgressHandler(metric);
  }

  static void _individualNFBUpdateCallback(Pointer<Void> handle) {
    final productivity = _obj[handle] as Productivity;

    productivity._individualNFBUpdateHandler();
  }

  static void _baselinesCallback(
      Pointer<Void> handle, Pointer<_NativeProductivityBaselines> baselines) {
    final productivity = _obj[handle] as Productivity;

    productivity._baselinesHandler(ProductivityBaselines._(baselines.ref));
  }

  static void _metricsCallback(
      Pointer<Void> handle, Pointer<_NativeProductivityMetrics> metrics) {
    final productivity = _obj[handle] as Productivity;

    productivity._metricsHandler(ProductivityMetrics._(metrics.ref));
  }

  static void _indexesCallback(
      Pointer<Void> handle, Pointer<_NativeProductivityIndexes> indexes) {
    final productivity = _obj[handle] as Productivity;

    productivity._indexesHandler(ProductivityIndexes._(indexes.ref));
  }
}

class Emotions extends _NativeOwner {
  Emotions(Device device) {
    if (device.empty) throw Exception("Empty device handle");
    _handle = _checkAndFreeNativeError((errorPtr) {
      return _CapsuleAPI._emotionsCreate(device._handle, errorPtr);
    });
    if (_handle == nullptr) {
      throw Exception("Failed to create Emotions");
    }
    _obj[_handle] = this;
    device._classifiers.add(_handle);
    _CapsuleAPI._setEmotionalStatesEventHandler(_handle,
        Pointer.fromFunction<_EmotionsHandler>(_emotionsChangedCallback));
    _CapsuleAPI._setEmotionsErrorHandler(
        _handle, Pointer.fromFunction<_StringHandler>(_emotionsErrorCallback));
  }

  Function(int, double, double, double, double, double) _emotionsHandler =
      (timestampMilli, attention, relaxation, cognitiveLoad, cognitiveControl,
          selfControl) {};

  set emotionsHandler(
      Function(int, double, double, double, double, double) handler) {
    _emotionsHandler = handler;
  }

  Function(String) _errorHandler = (error) {};

  set errorHandler(Function(String) handler) {
    _errorHandler = handler;
  }

  static void _emotionsChangedCallback(
      Pointer<Void> handle, Pointer<_NativeEmotionsState> emotionsPointer) {
    var emotions = _obj[handle] as Emotions;
    var emotionsState = emotionsPointer.ref;
    emotions._emotionsHandler(
        emotionsState.timestampMilli,
        emotionsState.attention,
        emotionsState.relaxation,
        emotionsState.cognitiveLoad,
        emotionsState.cognitiveControl,
        emotionsState.selfControl);
  }

  static void _emotionsErrorCallback(
      Pointer<Void> handle, Pointer<Utf8> errorPointer) {
    var emotions = _obj[handle] as Emotions;
    emotions._errorHandler(errorPointer.toDartString());
  }
}

class NFBCalibrator extends _NativeOwner {
  NFBCalibrator(Device device) {
    if (device.empty) throw Exception("Empty device handle");
    _handle = _CapsuleAPI._nfbCalibratorCreate(device._handle);
    if (_handle == nullptr) {
      throw Exception("Failed to create NFBCalibrator");
    }
    _obj[_handle] = this;
    device._classifiers.add(_handle);
    _CapsuleAPI._setOnIndividualCalibrationStageFinishedHandler(
        _handle, Pointer.fromFunction<_Handler>(_stageCallback));
    _CapsuleAPI._setOnIndividualCalibratedHandler(_handle,
        Pointer.fromFunction<_IndividualNFBHandler>(_calibratedCallback));
  }

  bool get calibrated => _CapsuleAPI._isNfbCalibrated(_handle);

  bool get calibrationReady => _CapsuleAPI._isNfbCalibrationReady(_handle);

  bool get calibrationFailed => _CapsuleAPI._hasNfbCalibrationFailed(_handle);

  IndividualNFBInfo get individualNFB {
    return _checkAndFreeNativeError((errorPtr) {
      final nativeInfo = malloc<_IndividualNFBInfo>();
      _CapsuleAPI._nfbCalibratorGetIndividualNFBData(
          _handle, nativeInfo, errorPtr);
      final info = IndividualNFBInfo._(nativeInfo.ref);
      malloc.free(nativeInfo);
      return info;
    });
  }

  void calibrateIndividualNFB(IndividualNFBCalibrationStage stage) {
    _checkAndFreeNativeError((errorPtr) =>
        _CapsuleAPI._nfbCalibratorCalibrateNFB(_handle, stage.index, errorPtr));
  }

  void calibrateIndividualNFBQuick() {
    _checkAndFreeNativeError((errorPtr) =>
        _CapsuleAPI._nfbCalibratorCalibrateNFBQuick(_handle, errorPtr));
  }

  void importIndividualNFB(IndividualNFBInfo individualNFB) {
    _checkAndFreeNativeError((errorPtr) {
      final nativeInfo = malloc<_IndividualNFBInfo>();
      individualNFB._toNative(nativeInfo);
      _CapsuleAPI._nfbCalibratorImportIndividualNFBData(
          _handle, nativeInfo, errorPtr);
      malloc.free(nativeInfo);
    });
  }

  set stageHandler(Function() handler) {
    _stageHandler = handler;
  }

  set calibratedHandler(Function(IndividualNFBInfo) handler) {
    _individualCalibratedHandler = handler;
  }

  static void _stageCallback(Pointer<Void> handle) {
    var nfbCalibrator = _obj[handle] as NFBCalibrator;
    nfbCalibrator._stageHandler();
  }

  Function() _stageHandler = () {};

  static void _calibratedCallback(
      Pointer<Void> handle, Pointer<_IndividualNFBInfo> individualNFB) {
    var nfbCalibrator = _obj[handle] as NFBCalibrator;
    nfbCalibrator
        ._individualCalibratedHandler(IndividualNFBInfo._(individualNFB.ref));
  }

  Function(IndividualNFBInfo) _individualCalibratedHandler = (individualNFB) {};
}

class NFBClassifier extends _NativeOwner {
  NFBClassifier(Device device) {
    if (device.empty) throw Exception("Empty device handle");
    _handle = _checkAndFreeNativeError(
        (errorPtr) => _CapsuleAPI._nfbCreate(device._handle, errorPtr));
    _init(device);
  }

  NFBClassifier.calibrated(Device device, NFBCalibrator calibrator) {
    if (device.empty) throw Exception("Empty device handle");
    if (calibrator.empty) throw Exception("Empty calibrator handle");
    _handle = _checkAndFreeNativeError((errorPtr) =>
        _CapsuleAPI._nfbCreateCalibrated(
            device._handle, calibrator._handle, errorPtr));
    _init(device);
  }

  void _init(Device device) {
    if (_handle == nullptr) {
      throw Exception("Failed to create NFBClassifier");
    }
    _obj[_handle] = this;
    device._classifiers.add(_handle);
    _CapsuleAPI._setNFBErrorEventHandler(
        _handle, Pointer.fromFunction<_StringHandler>(_nfbErrorCallback));
    _CapsuleAPI._setNFBUserStateChangedEventHandler(_handle,
        Pointer.fromFunction<_UserStateHandler>(_nfbUserStateChangedCallback));
  }

  set errorHandler(Function(String) value) {
    _nfbErrorHandler = value;
  }

  set userStateHandler(
      Function(int timestampMilli, double delta, double theta, double alpha,
              double smr, double beta)
          handler) {
    _nfbUserStateHandler = handler;
  }

  Function(String) _nfbErrorHandler = (error) {};
  Function(int, double, double, double, double, double) _nfbUserStateHandler =
      (timestampMilli, delta, theta, alpha, smr, beta) {};

  static void _nfbErrorCallback(Pointer<Void> handle, Pointer<Utf8> error) {
    var nfb = _obj[handle] as NFBClassifier;
    nfb._nfbErrorHandler(error.toDartString());
  }

  static void _nfbUserStateChangedCallback(
      Pointer<Void> handle, Pointer<_NFBUserState> userState) {
    var nfb = _obj[handle] as NFBClassifier;
    nfb._nfbUserStateHandler(
        userState.ref.timestampMilli,
        userState.ref.delta,
        userState.ref.theta,
        userState.ref.alpha,
        userState.ref.smr,
        userState.ref.beta);
  }
}

class PhysiologicalStates extends _NativeOwner {
  PhysiologicalStates(Device device) {
    if (device.empty) throw Exception("Empty device handle");

    _handle = _checkAndFreeNativeError((errorPtr) {
      return _CapsuleAPI._physiologicalStatesCreate(device._handle, errorPtr);
    });
    _init(device);
  }

  void _init(Device device) {
    if (_handle == nullptr) {
      throw Exception("Failed to create PhysiologicalStates");
    }
    _obj[_handle] = this;
    device._classifiers.add(_handle);
    _checkAndFreeNativeError((errorPtr) {
      _CapsuleAPI._setPhysiologicalStatesCalibrationProgressHandler(
          _handle,
          Pointer.fromFunction<_FloatHandler>(_calibrationProgressCallback),
          errorPtr);
      _CapsuleAPI._setPhysiologicalStatesIndividualNFBUpdateHandler(
          _handle,
          Pointer.fromFunction<_Handler>(_individualNFBUpdateCallback),
          errorPtr);
      _CapsuleAPI._setPhysiologicalBaselinesHandler(
          _handle,
          Pointer.fromFunction<_PhysiologicalBaselinesHandler>(
              _baselinesCallback),
          errorPtr);
      _CapsuleAPI._setPhysiologicalStatesUpdateHandler(
          _handle,
          Pointer.fromFunction<_PhysiologicalStatesHandler>(_metricsCallback),
          errorPtr);
    });
  }

  void importBaselines(PhysiologicalBaselines baselines) {
    _checkAndFreeNativeError((errorPtr) {
      final nativeBaselines = malloc<_NativePhysiologicalBaselines>();
      baselines._toNative(nativeBaselines);
      _CapsuleAPI._physiologicalStatesImportBaselines(
          _handle, nativeBaselines, errorPtr);
      malloc.free(nativeBaselines);
    });
  }

  void startBaselineCalibration() {
    _CapsuleAPI._physiologicalStatesStartBaselineCalibration(_handle);
  }

  Function(double) _calibrationProgressHandler = (progress) {};
  Function() _individualNFBUpdateHandler = () {};
  Function(PhysiologicalBaselines) _baselinesHandler = (baselines) {};
  Function(PhysiologicalStatesValues) _statesHandler = (metrics) {};

  set calibrationProgressHandler(Function(double) handler) {
    _calibrationProgressHandler = handler;
  }

  set individualNFBUpdateHandler(Function() handler) {
    _individualNFBUpdateHandler = handler;
  }

  set baselinesHandler(Function(PhysiologicalBaselines) handler) {
    _baselinesHandler = handler;
  }

  set valuesHandler(Function(PhysiologicalStatesValues) handler) {
    _statesHandler = handler;
  }

  static void _calibrationProgressCallback(
      Pointer<Void> handle, double metric) {
    final states = _obj[handle] as PhysiologicalStates;

    states._calibrationProgressHandler(metric);
  }

  static void _individualNFBUpdateCallback(Pointer<Void> handle) {
    final states = _obj[handle] as PhysiologicalStates;

    states._individualNFBUpdateHandler();
  }

  static void _baselinesCallback(
      Pointer<Void> handle, Pointer<_NativePhysiologicalBaselines> baselines) {
    final states = _obj[handle] as PhysiologicalStates;

    states._baselinesHandler(PhysiologicalBaselines._(baselines.ref));
  }

  static void _metricsCallback(
      Pointer<Void> handle, Pointer<_NativePhysiologicalStates> values) {
    final states = _obj[handle] as PhysiologicalStates;

    states._statesHandler(PhysiologicalStatesValues._(values.ref));
  }
}

/// Implementation

void _checkSizes() {
  assert(sizeOf<_NativeError>() == 264);
  assert(sizeOf<_NativePoint3d>() == 12);
  assert(sizeOf<_NativeCardioData>() == 24);
  assert(sizeOf<_NFBUserState>() == 32);
  assert(sizeOf<_NativeEmotionsState>() == 32);
  assert(sizeOf<_IndividualNFBInfo>() == 48);
  assert(sizeOf<_NativeProductivityBaselines>() == 32);
  assert(sizeOf<_NativeProductivityMetrics>() == 72);
  assert(sizeOf<_NativeProductivityIndexes>() == 48);
  assert(sizeOf<_NativePhysiologicalStates>() == 40);
  assert(sizeOf<_NativePhysiologicalBaselines>() == 32);
}

class _NativeError extends Struct {
  @Array(256)
  external Array<Char> message;
  @Bool()
  external bool success;
  @Uint32()
  external int code;
}

class _NFBUserState extends Struct {
  @Int64()
  external int timestampMilli;
  @Float()
  external double delta, theta, alpha, smr, beta;
}

class _NativeEmotionsState extends Struct {
  @Int64()
  external int timestampMilli;
  @Float()
  external double attention;
  @Float()
  external double relaxation;
  @Float()
  external double cognitiveLoad;
  @Float()
  external double cognitiveControl;
  @Float()
  external double selfControl;
}

class ProductivityBaselines {
  int timestampMilli;
  double gravity, productivity, fatigue, reverseFatigue, relax, concentration;

  ProductivityBaselines._(_NativeProductivityBaselines native)
      : timestampMilli = native.timestampMilli,
        gravity = native.gravity,
        productivity = native.productivity,
        fatigue = native.fatigue,
        reverseFatigue = native.reverseFatigue,
        relax = native.relax,
        concentration = native.concentration;

  void _toNative(Pointer<_NativeProductivityBaselines> native) {
    native.ref.timestampMilli = timestampMilli;
    native.ref.gravity = gravity;
    native.ref.productivity = productivity;
    native.ref.fatigue = fatigue;
    native.ref.reverseFatigue = reverseFatigue;
    native.ref.relax = relax;
    native.ref.concentration = concentration;
  }
}

class _NativeProductivityBaselines extends Struct {
  @Int64()
  external int timestampMilli;
  @Float()
  external double gravity,
      productivity,
      fatigue,
      reverseFatigue,
      relax,
      concentration;
}

enum ProductivityRecommendationValue {
  noRecommendation,
  involvement,
  relaxation,
  slightFatigue,
  severeFatigue,
  chronicFatigue
}

enum ProductivityStressValue { noStress, anxiety, stress }

class ProductivityIndexes {
  int timestampMilli;
  ProductivityRecommendationValue relaxation;
  ProductivityStressValue stress;
  double gravityBaseline,
      productivityBaseline,
      fatigueBaseline,
      reverseFatigueBaseline,
      relaxBaseline,
      concentrationBaseline;
  bool hasArtifacts;

  ProductivityIndexes._(_NativeProductivityIndexes native)
      : timestampMilli = native.timestampMilli,
        relaxation = ProductivityRecommendationValue.values[native.relaxation],
        stress = ProductivityStressValue.values[native.stress],
        gravityBaseline = native.gravityBaseline,
        productivityBaseline = native.productivityBaseline,
        fatigueBaseline = native.fatigueBaseline,
        reverseFatigueBaseline = native.reverseFatigueBaseline,
        relaxBaseline = native.relaxBaseline,
        concentrationBaseline = native.concentrationBaseline,
        hasArtifacts = native.hasArtifacts;
}

class _NativeProductivityIndexes extends Struct {
  @Int64()
  external int timestampMilli;
  @Int32()
  external int relaxation;
  @Int32()
  external int stress;
  @Float()
  external double gravityBaseline,
      productivityBaseline,
      fatigueBaseline,
      reverseFatigueBaseline,
      relaxBaseline,
      concentrationBaseline;
  @Bool()
  external bool hasArtifacts;
}

enum FatigueGrowthRate { none, low, medium, high }

class ProductivityMetrics {
  int timestampMilli;
  double fatigueScore,
      reverseFatigueScore,
      gravityScore,
      relaxationScore,
      concentrationScore,
      productivityScore,
      currentValue,
      alpha,
      productivityBaseline,
      accumulatedFatigue;
  FatigueGrowthRate fatigueGrowthRate;
  List<int> artifacts;

  ProductivityMetrics._(_NativeProductivityMetrics native)
      : timestampMilli = native.timestampMilli,
        fatigueScore = native.fatigueScore,
        reverseFatigueScore = native.reverseFatigueScore,
        gravityScore = native.gravityScore,
        relaxationScore = native.relaxationScore,
        concentrationScore = native.concentrationScore,
        productivityScore = native.productivityScore,
        currentValue = native.currentValue,
        alpha = native.alpha,
        productivityBaseline = native.productivityBaseline,
        accumulatedFatigue = native.accumulatedFatigue,
        fatigueGrowthRate = FatigueGrowthRate.values[native.fatigueGrowthRate],
        artifacts = List.generate(native.artifactsSize, (index) {
          return native.artifactsData[index];
        });
}

class _NativeProductivityMetrics extends Struct {
  @Int64()
  external int timestampMilli;
  @Float()
  external double fatigueScore,
      reverseFatigueScore,
      gravityScore,
      relaxationScore,
      concentrationScore,
      productivityScore,
      currentValue,
      alpha,
      productivityBaseline,
      accumulatedFatigue;
  @Int32()
  external int fatigueGrowthRate;
  @Int32()
  external int pad;
  external Pointer<Uint8> artifactsData;
  @Uint64()
  external int artifactsSize;
}

class PhysiologicalStatesValues {
  int timestampMilli;
  double relaxation, fatigue, none, concentration, involvement, stress;
  bool nfbArtifacts, cardioArtifacts;

  PhysiologicalStatesValues._(_NativePhysiologicalStates native)
      : timestampMilli = native.timestampMilli,
        relaxation = native.relaxation,
        fatigue = native.fatigue,
        none = native.none,
        concentration = native.concentration,
        involvement = native.involvement,
        stress = native.stress,
        nfbArtifacts = native.nfbArtifacts,
        cardioArtifacts = native.cardioArtifacts;
}

class _NativePhysiologicalStates extends Struct {
  @Int64()
  external int timestampMilli;
  @Float()
  external double relaxation, fatigue, none, concentration, involvement, stress;
  @Bool()
  external bool nfbArtifacts, cardioArtifacts;
}

class PhysiologicalBaselines {
  int timestampMilli;
  double alpha, beta, alphaGravity, betaGravity, concentration;

  PhysiologicalBaselines._(_NativePhysiologicalBaselines native)
      : timestampMilli = native.timestampMilli,
        alpha = native.alpha,
        beta = native.beta,
        alphaGravity = native.alpha,
        betaGravity = native.betaGravity,
        concentration = native.concentration;

  void _toNative(Pointer<_NativePhysiologicalBaselines> native) {
    native.ref.timestampMilli = timestampMilli;
    native.ref.alpha = alpha;
    native.ref.beta = beta;
    native.ref.alphaGravity = alphaGravity;
    native.ref.betaGravity = betaGravity;
    native.ref.concentration = concentration;
  }
}

class _NativePhysiologicalBaselines extends Struct {
  @Int64()
  external int timestampMilli;
  @Float()
  external double alpha, beta, alphaGravity, betaGravity, concentration;
}

typedef _GetStringStatic = Pointer<Utf8> Function();
typedef _StringHandler = Void Function(Pointer<Void>, Pointer<Utf8>);
typedef _PointerHandler = Void Function(Pointer<Void>, Pointer<Void>);
typedef _Handler = Void Function(Pointer<Void>);
typedef _EnumHandler = Void Function(Pointer<Void>, Int32);
typedef _CharHandler = Void Function(Pointer<Void>, Int8);
typedef _FloatHandler = Void Function(Pointer<Void>, Float);
typedef _DeviceListHandler = Void Function(
    Pointer<Void>, Pointer<Void>, Uint32);
typedef _UserStateHandler = Void Function(
    Pointer<Void>, Pointer<_NFBUserState>);
typedef _ProductivityMetricsHandler = Void Function(
    Pointer<Void>, Pointer<_NativeProductivityMetrics>);
typedef _ProductivityBaselinesHandler = Void Function(
    Pointer<Void>, Pointer<_NativeProductivityBaselines>);
typedef _PhysiologicalBaselinesHandler = Void Function(
    Pointer<Void>, Pointer<_NativePhysiologicalBaselines>);
typedef _PhysiologicalStatesHandler = Void Function(
    Pointer<Void>, Pointer<_NativePhysiologicalStates>);
typedef _EmotionsHandler = Void Function(
    Pointer<Void>, Pointer<_NativeEmotionsState>);
typedef _CardioDataHandler = Void Function(
    Pointer<Void>, Pointer<_NativeCardioData>);
typedef _ProductivityIndexesHandler = Void Function(
    Pointer<Void>, Pointer<_NativeProductivityIndexes>);
typedef _IndividualNFBHandler = Void Function(
    Pointer<Void>, Pointer<_IndividualNFBInfo>);

typedef _DartCallback = void Function(
    Pointer<Void>, Pointer<NativeFunction<_Handler>>);
typedef _NativeCallback = Void Function(
    Pointer<Void>, Pointer<NativeFunction<_Handler>>);

typedef _DartCallbackWithError = void Function(
    Pointer<Void>, Pointer<NativeFunction<_Handler>>, Pointer<_NativeError>);
typedef _NativeCallbackWithError = Void Function(
    Pointer<Void>, Pointer<NativeFunction<_Handler>>, Pointer<_NativeError>);

typedef _DartCardioDataCallback = void Function(Pointer<Void>,
    Pointer<NativeFunction<_CardioDataHandler>>, Pointer<_NativeError>);
typedef _NativeCardioDataCallback = Void Function(Pointer<Void>,
    Pointer<NativeFunction<_CardioDataHandler>>, Pointer<_NativeError>);

typedef _DartEmotionsCallback = void Function(
    Pointer<Void>, Pointer<NativeFunction<_EmotionsHandler>>);
typedef _NativeEmotionsCallback = Void Function(
    Pointer<Void>, Pointer<NativeFunction<_EmotionsHandler>>);

typedef _DartPointerCallback = void Function(
    Pointer<Void>, Pointer<NativeFunction<_PointerHandler>>);
typedef _NativePointerCallback = Void Function(
    Pointer<Void>, Pointer<NativeFunction<_PointerHandler>>);

typedef _DartPointerCallbackWithError = void Function(Pointer<Void>,
    Pointer<NativeFunction<_PointerHandler>>, Pointer<_NativeError>);
typedef _NativePointerCallbackWithError = Void Function(Pointer<Void>,
    Pointer<NativeFunction<_PointerHandler>>, Pointer<_NativeError>);

typedef _DartEnumCallback = void Function(
    Pointer<Void>, Pointer<NativeFunction<_EnumHandler>>);
typedef _NativeEnumCallback = Void Function(
    Pointer<Void>, Pointer<NativeFunction<_EnumHandler>>);

typedef _DartCharCallback = void Function(
    Pointer<Void>, Pointer<NativeFunction<_CharHandler>>);
typedef _NativeCharCallback = Void Function(
    Pointer<Void>, Pointer<NativeFunction<_CharHandler>>);

typedef _DartFloatCallback = void Function(
    Pointer<Void>, Pointer<NativeFunction<_FloatHandler>>);
typedef _NativeFloatCallback = Void Function(
    Pointer<Void>, Pointer<NativeFunction<_FloatHandler>>);

typedef _DartFloatCallbackWithError = void Function(Pointer<Void>,
    Pointer<NativeFunction<_FloatHandler>>, Pointer<_NativeError>);
typedef _NativeFloatCallbackWithError = Void Function(Pointer<Void>,
    Pointer<NativeFunction<_FloatHandler>>, Pointer<_NativeError>);

typedef _DartUserStateChangedCallback = void Function(
    Pointer<Void>, Pointer<NativeFunction<_UserStateHandler>>);
typedef _NativeUserStateChangedCallback = Void Function(
    Pointer<Void>, Pointer<NativeFunction<_UserStateHandler>>);

typedef _DartMetricsChangedCallback = void Function(
    Pointer<Void>, Pointer<NativeFunction<_ProductivityMetricsHandler>>);
typedef _NativeMetricsChangedCallback = Void Function(
    Pointer<Void>, Pointer<NativeFunction<_ProductivityMetricsHandler>>);

typedef _DartProductivityBaselinesCallback = void Function(
    Pointer<Void>, Pointer<NativeFunction<_ProductivityBaselinesHandler>>);
typedef _NativeProductivityBaselinesCallback = Void Function(
    Pointer<Void>, Pointer<NativeFunction<_ProductivityBaselinesHandler>>);

typedef _DartPhysiologicalBaselinesCallback = void Function(
    Pointer<Void>,
    Pointer<NativeFunction<_PhysiologicalBaselinesHandler>>,
    Pointer<_NativeError>);
typedef _NativePhysiologicalBaselinesCallback = Void Function(
    Pointer<Void>,
    Pointer<NativeFunction<_PhysiologicalBaselinesHandler>>,
    Pointer<_NativeError>);

typedef _DartPhysiologicalStatesCallback = void Function(
    Pointer<Void>,
    Pointer<NativeFunction<_PhysiologicalStatesHandler>>,
    Pointer<_NativeError>);
typedef _NativePhysiologicalStatesCallback = Void Function(
    Pointer<Void>,
    Pointer<NativeFunction<_PhysiologicalStatesHandler>>,
    Pointer<_NativeError>);

typedef _DartProductivityIndexesChangedCallback = void Function(
    Pointer<Void>, Pointer<NativeFunction<_ProductivityIndexesHandler>>);
typedef _NativeProductivityIndexesChangedCallback = Void Function(
    Pointer<Void>, Pointer<NativeFunction<_ProductivityIndexesHandler>>);

typedef _DartStringCallback = void Function(
    Pointer<Void>, Pointer<NativeFunction<_StringHandler>>);
typedef _NativeStringCallback = Void Function(
    Pointer<Void>, Pointer<NativeFunction<_StringHandler>>);

typedef _DartDeviceListCallback = void Function(
    Pointer<Void>, Pointer<NativeFunction<_DeviceListHandler>>);
typedef _NativeDeviceListCallback = Void Function(
    Pointer<Void>, Pointer<NativeFunction<_DeviceListHandler>>);

typedef _DartIndividualNFBChangedCallback = void Function(
    Pointer<Void>, Pointer<NativeFunction<_IndividualNFBHandler>>);
typedef _NativeIndividualNFBChangedCallback = Void Function(
    Pointer<Void>, Pointer<NativeFunction<_IndividualNFBHandler>>);

class _CapsuleAPI {
  static final DynamicLibrary _capsuleClientLib = Platform.isWindows
      ? Platform.environment.containsKey('FLUTTER_TEST')
          ? DynamicLibrary.open("windows/CapsuleClient.dll")
          : DynamicLibrary.open("CapsuleClient.dll")
      : (Platform.isMacOS || Platform.isIOS)
          ? DynamicLibrary.open("libCapsuleClient.dylib")
          : DynamicLibrary.open("libCapsuleClient.so");

  static final Pointer<Utf8> Function() _getVersionString = _capsuleClientLib
      .lookupFunction<_GetStringStatic, Pointer<Utf8> Function()>(
          "clCCapsule_GetVersionString");

  static final void Function(Pointer<Void>, bool, Pointer<_NativeError>)
      _deviceConnect = _capsuleClientLib.lookupFunction<
          Void Function(Pointer<Void>, Bool, Pointer<_NativeError>),
          void Function(
              Pointer<Void>, bool, Pointer<_NativeError>)>("clCDevice_Connect");

  static final void Function(Pointer<Void>, Pointer<_NativeError>)
      _deviceDisconnect = _capsuleClientLib.lookupFunction<
          Void Function(Pointer<Void>, Pointer<_NativeError>),
          void Function(
              Pointer<Void>, Pointer<_NativeError>)>("clCDevice_Disconnect");

  static final void Function(Pointer<Void>, Pointer<_NativeError>)
      _deviceStart = _capsuleClientLib.lookupFunction<
          Void Function(Pointer<Void>, Pointer<_NativeError>),
          void Function(
              Pointer<Void>, Pointer<_NativeError>)>("clCDevice_Start");

  static final void Function(Pointer<Void>, Pointer<_NativeError>) _deviceStop =
      _capsuleClientLib.lookupFunction<
          Void Function(Pointer<Void>, Pointer<_NativeError>),
          void Function(
              Pointer<Void>, Pointer<_NativeError>)>("clCDevice_Stop");

  static final int Function(Pointer<Void>, Pointer<_NativeError>)
      _isDeviceConnected = _capsuleClientLib.lookupFunction<
          Int32 Function(Pointer<Void>, Pointer<_NativeError>),
          int Function(
              Pointer<Void>, Pointer<_NativeError>)>("clCDevice_IsConnected");

  static final int Function(Pointer<Void>, Pointer<_NativeError>)
      _batteryCharge = _capsuleClientLib.lookupFunction<
          Uint8 Function(Pointer<Void>, Pointer<_NativeError>),
          int Function(Pointer<Void>,
              Pointer<_NativeError>)>("clCDevice_GetBatteryCharge");

  static final int Function(Pointer<Void>) _deviceMode =
      _capsuleClientLib.lookupFunction<Int32 Function(Pointer<Void>),
          int Function(Pointer<Void>)>("clCDevice_GetMode");

  static final Pointer<Void> Function(Pointer<Void>, Pointer<_NativeError>)
      _deviceGetInfo = _capsuleClientLib.lookupFunction<
          Pointer<Void> Function(Pointer<Void>, Pointer<_NativeError>),
          Pointer<Void> Function(
              Pointer<Void>, Pointer<_NativeError>)>("clCDevice_GetInfo");

  static final double Function(Pointer<Void>, Pointer<_NativeError>)
      _deviceGetEEGSampleRate = _capsuleClientLib.lookupFunction<
          Float Function(Pointer<Void>, Pointer<_NativeError>),
          double Function(Pointer<Void>,
              Pointer<_NativeError>)>("clCDevice_GetEEGSampleRate");

  static final double Function(Pointer<Void>, Pointer<_NativeError>)
      _deviceGetPPGSampleRate = _capsuleClientLib.lookupFunction<
          Float Function(Pointer<Void>, Pointer<_NativeError>),
          double Function(Pointer<Void>,
              Pointer<_NativeError>)>("clCDevice_GetPPGSampleRate");

  static final double Function(Pointer<Void>, Pointer<_NativeError>)
      _deviceGetMEMSSampleRate = _capsuleClientLib.lookupFunction<
          Float Function(Pointer<Void>, Pointer<_NativeError>),
          double Function(Pointer<Void>,
              Pointer<_NativeError>)>("clCDevice_GetMEMSSampleRate");

  static final int Function(Pointer<Void>, Pointer<_NativeError>)
      _deviceGetPPGIrAmplitude = _capsuleClientLib.lookupFunction<
          Int32 Function(Pointer<Void>, Pointer<_NativeError>),
          int Function(Pointer<Void>,
              Pointer<_NativeError>)>("clCDevice_GetPPGIrAmplitude");

  static final int Function(Pointer<Void>, Pointer<_NativeError>)
      _deviceGetPPGRedAmplitude = _capsuleClientLib.lookupFunction<
          Int32 Function(Pointer<Void>, Pointer<_NativeError>),
          int Function(Pointer<Void>,
              Pointer<_NativeError>)>("clCDevice_GetPPGRedAmplitude");

  static final void Function(Pointer<Void>) _update = _capsuleClientLib
      .lookup<NativeFunction<Void Function(Pointer<Void>)>>(
          "clCDeviceLocator_Update")
      .asFunction();

  static final void Function(bool) _setSingleThreaded = _capsuleClientLib
      .lookup<NativeFunction<Void Function(Bool)>>(
          "clCCapsule_SetSingleThreaded")
      .asFunction();

  static final void Function(int) _setLogLevel = _capsuleClientLib
      .lookup<NativeFunction<Void Function(Int32)>>("clCCapsule_SetLogLevel")
      .asFunction();

  static final int Function() _getLogLevel = _capsuleClientLib
      .lookup<NativeFunction<Int32 Function()>>("clCCapsule_GetLogLevel")
      .asFunction();

  static final Pointer<Void> Function(Pointer<Void>, Pointer<_NativeError>)
      _deviceGetChannelNames = _capsuleClientLib.lookupFunction<
          Pointer<Void> Function(Pointer<Void>, Pointer<_NativeError>),
          Pointer<Void> Function(Pointer<Void>,
              Pointer<_NativeError>)>("clCDevice_GetChannelNames");

  static final void Function(Pointer<Void>) _destroyDeviceLocator =
      _capsuleClientLib.lookupFunction<Void Function(Pointer<Void>),
          void Function(Pointer<Void>)>("clCDeviceLocator_Destroy");

  static final Pointer<Void> Function(Pointer<_NativeError>)
      _createDeviceLocator = _capsuleClientLib.lookupFunction<
          Pointer<Void> Function(Pointer<_NativeError>),
          Pointer<Void> Function(
              Pointer<_NativeError>)>("clCDeviceLocator_Create");

  static final Pointer<Void> Function(Pointer<Utf8>, Pointer<_NativeError>)
      _createDeviceLocatorWithLogDirectory = _capsuleClientLib.lookupFunction<
              Pointer<Void> Function(Pointer<Utf8>, Pointer<_NativeError>),
              Pointer<Void> Function(Pointer<Utf8>, Pointer<_NativeError>)>(
          "clCDeviceLocator_CreateWithLogDirectory");

  static final int Function(Pointer<Void>) _resistancesGetCount =
      _capsuleClientLib.lookupFunction<Int32 Function(Pointer<Void>),
          int Function(Pointer<Void>)>("clCResistance_GetCount");

  static final double Function(Pointer<Void>, int) _resistancesGetResistance =
      _capsuleClientLib.lookupFunction<Float Function(Pointer<Void>, Int32),
          double Function(Pointer<Void>, int)>("clCResistance_GetValue");

  static final Pointer<Utf8> Function(Pointer<Void>, int)
      _resistancesGetChannelName = _capsuleClientLib.lookupFunction<
          Pointer<Utf8> Function(Pointer<Void>, Int32),
          Pointer<Utf8> Function(
              Pointer<Void>, int)>("clCResistance_GetChannelName");

  static final int Function(Pointer<Void>) _memsGetCount =
      _capsuleClientLib.lookupFunction<Int32 Function(Pointer<Void>),
          int Function(Pointer<Void>)>("clCMEMSTimedData_GetCount");

  static final _NativePoint3d Function(Pointer<Void>, int)
      _memsGetAccelerometer = _capsuleClientLib.lookupFunction<
          _NativePoint3d Function(Pointer<Void>, Int32),
          _NativePoint3d Function(
              Pointer<Void>, int)>("clCMEMSTimedData_GetAccelerometer");

  static final _NativePoint3d Function(Pointer<Void>, int) _memsGetGyroscope =
      _capsuleClientLib.lookupFunction<
          _NativePoint3d Function(Pointer<Void>, Int32),
          _NativePoint3d Function(
              Pointer<Void>, int)>("clCMEMSTimedData_GetGyroscope");

  static final int Function(Pointer<Void>, int) _memsGetTimestampMilli =
      _capsuleClientLib.lookupFunction<
          Uint64 Function(Pointer<Void>, Int32),
          int Function(
              Pointer<Void>, int)>("clCMEMSTimedData_GetTimestampMilli");

  static final int Function(Pointer<Void>) _ppgGetCount =
      _capsuleClientLib.lookupFunction<Int32 Function(Pointer<Void>),
          int Function(Pointer<Void>)>("clCPPGTimedData_GetCount");

  static final double Function(Pointer<Void>, int) _ppgGetValue =
      _capsuleClientLib.lookupFunction<Float Function(Pointer<Void>, Int32),
          double Function(Pointer<Void>, int)>("clCPPGTimedData_GetValue");

  static final int Function(Pointer<Void>, int) _ppgGetTimestampMilli =
      _capsuleClientLib.lookupFunction<
          Uint64 Function(Pointer<Void>, Int32),
          int Function(
              Pointer<Void>, int)>("clCPPGTimedData_GetTimestampMilli");

  static final int Function(Pointer<Void>, Pointer<_NativeError>)
      _deviceChannelNamesGetCount = _capsuleClientLib.lookupFunction<
              Int32 Function(Pointer<Void>, Pointer<_NativeError>),
              int Function(Pointer<Void>, Pointer<_NativeError>)>(
          "clCDevice_ChannelNames_GetChannelsCount");

  static final Pointer<Utf8> Function(Pointer<Void>, int, Pointer<_NativeError>)
      _deviceChannelNamesGetNameByIndex = _capsuleClientLib
          .lookupFunction<
                  Pointer<Utf8> Function(
                      Pointer<Void>, Int32, Pointer<_NativeError>),
                  Pointer<Utf8> Function(
                      Pointer<Void>, int, Pointer<_NativeError>)>(
              "clCDevice_ChannelNames_GetChannelNameByIndex");

  static final _DartPointerCallback _setResistancesEventHandler =
      _capsuleClientLib.lookupFunction<_NativePointerCallback,
          _DartPointerCallback>('clCDevice_SetOnResistanceUpdateEvent');

  static final _DartCharCallback _setBatteryEventHandler =
      _capsuleClientLib.lookupFunction<_NativeCharCallback, _DartCharCallback>(
          'clCDevice_SetOnBatteryChargeUpdateEvent');

  static final _DartEnumCallback _setDeviceModeEventHandler =
      _capsuleClientLib.lookupFunction<_NativeEnumCallback, _DartEnumCallback>(
          'clCDevice_SetOnModeSwitchedEvent');

  static final _DartPointerCallback _setDeviceEEGEventHandler =
      _capsuleClientLib.lookupFunction<_NativePointerCallback,
          _DartPointerCallback>('clCDevice_SetOnEEGDataEvent');

  static final _DartPointerCallback _setDeviceEEGArtifactsEventHandler =
      _capsuleClientLib.lookupFunction<_NativePointerCallback,
          _DartPointerCallback>('clCDevice_SetOnEEGArtifactsEvent');

  static final _DartPointerCallback _setDevicePSDEventHandler =
      _capsuleClientLib.lookupFunction<_NativePointerCallback,
          _DartPointerCallback>('clCDevice_SetOnPSDDataEvent');

  static final _DartStringCallback _setDeviceErrorEventHandler =
      _capsuleClientLib.lookupFunction<_NativeStringCallback,
          _DartStringCallback>('clCDevice_SetOnErrorEvent');

  static final void Function(Pointer<Void>, int, int, Pointer<_NativeError>)
      _requestDevices = _capsuleClientLib.lookupFunction<
          Void Function(Pointer<Void>, Uint32, Uint32, Pointer<_NativeError>),
          void Function(Pointer<Void>, int, int,
              Pointer<_NativeError>)>("clCDeviceLocator_RequestDevices");

  static final Pointer<Void> Function(
          Pointer<Void>, Pointer<Utf8>, Pointer<_NativeError>) _lockDevice =
      _capsuleClientLib.lookupFunction<
          Pointer<Void> Function(
              Pointer<Void>, Pointer<Utf8>, Pointer<_NativeError>),
          Pointer<Void> Function(Pointer<Void>, Pointer<Utf8>,
              Pointer<_NativeError>)>("clCDeviceLocator_CreateDevice");

  static final void Function(Pointer<Void>) _releaseDevice =
      _capsuleClientLib.lookupFunction<Void Function(Pointer<Void>),
          void Function(Pointer<Void>)>("clCDevice_Release");

  static final _DartDeviceListCallback _setDeviceLocatorDevicesEvent =
      _capsuleClientLib.lookupFunction<_NativeDeviceListCallback,
          _DartDeviceListCallback>('clCDeviceLocator_SetOnDeviceListEvent');

  static final int Function(Pointer<Void>, Pointer<_NativeError>)
      _devicesGetCount = _capsuleClientLib.lookupFunction<
          Int32 Function(Pointer<Void>, Pointer<_NativeError>),
          int Function(Pointer<Void>,
              Pointer<_NativeError>)>("clCDeviceInfoList_GetCount");

  static final Pointer<Utf8> Function(Pointer<Void>) _deviceGetID =
      _capsuleClientLib.lookupFunction<Pointer<Utf8> Function(Pointer<Void>),
          Pointer<Utf8> Function(Pointer<Void>)>("clCDeviceInfo_GetSerial");

  static final Pointer<Utf8> Function(Pointer<Void>) _deviceGetName =
      _capsuleClientLib.lookupFunction<Pointer<Utf8> Function(Pointer<Void>),
          Pointer<Utf8> Function(Pointer<Void>)>("clCDeviceInfo_GetName");

  static final int Function(Pointer<Void>) _deviceGetType =
      _capsuleClientLib.lookupFunction<Uint32 Function(Pointer<Void>),
          int Function(Pointer<Void>)>("clCDeviceInfo_GetType");

  static final Pointer<Void> Function(Pointer<Void>, int, Pointer<_NativeError>)
      _devicesGetDevice = _capsuleClientLib.lookupFunction<
          Pointer<Void> Function(Pointer<Void>, Int32, Pointer<_NativeError>),
          Pointer<Void> Function(Pointer<Void>, int,
              Pointer<_NativeError>)>("clCDeviceInfoList_GetDeviceInfo");

  static final _DartEnumCallback _setDeviceConnectionEvent =
      _capsuleClientLib.lookupFunction<_NativeEnumCallback, _DartEnumCallback>(
          'clCDevice_SetOnConnectionStatusChangedEvent');

  static final int Function(Pointer<Void>, Pointer<_NativeError>)
      _eegTimedDataGetChannelsCount = _capsuleClientLib.lookupFunction<
          Int32 Function(Pointer<Void>, Pointer<_NativeError>),
          int Function(Pointer<Void>,
              Pointer<_NativeError>)>("clCEEGTimedData_GetChannelsCount");

  static final int Function(Pointer<Void>, Pointer<_NativeError>)
      _eegTimedDataGetSamplesCount = _capsuleClientLib.lookupFunction<
          Int32 Function(Pointer<Void>, Pointer<_NativeError>),
          int Function(Pointer<Void>,
              Pointer<_NativeError>)>("clCEEGTimedData_GetSamplesCount");

  static final double Function(Pointer<Void>, int, int, Pointer<_NativeError>)
      _eegTimedDataGetRawValue = _capsuleClientLib.lookupFunction<
          Float Function(Pointer<Void>, Int32, Int32, Pointer<_NativeError>),
          double Function(Pointer<Void>, int, int,
              Pointer<_NativeError>)>("clCEEGTimedData_GetRawValue");

  static final double Function(Pointer<Void>, int, int, Pointer<_NativeError>)
      _eegTimedDataGetProcessedValue = _capsuleClientLib.lookupFunction<
          Float Function(Pointer<Void>, Int32, Int32, Pointer<_NativeError>),
          double Function(Pointer<Void>, int, int,
              Pointer<_NativeError>)>("clCEEGTimedData_GetProcessedValue");

  static final int Function(Pointer<Void>, int, Pointer<_NativeError>)
      _eegTimedDataGetTimestampMilli = _capsuleClientLib.lookupFunction<
          Uint64 Function(Pointer<Void>, Uint64, Pointer<_NativeError>),
          int Function(Pointer<Void>, int,
              Pointer<_NativeError>)>("clCEEGTimedData_GetTimestampMilli");

  static final int Function(Pointer<Void>, Pointer<_NativeError>)
      _eegArtifactsGetChannelsCount = _capsuleClientLib.lookupFunction<
          Int32 Function(Pointer<Void>, Pointer<_NativeError>),
          int Function(Pointer<Void>,
              Pointer<_NativeError>)>("clCEEGArtifacts_GetChannelsCount");

  static final int Function(Pointer<Void>, Pointer<_NativeError>)
      _eegArtifactsGetTimestampMilli = _capsuleClientLib.lookupFunction<
          Uint64 Function(Pointer<Void>, Pointer<_NativeError>),
          int Function(Pointer<Void>,
              Pointer<_NativeError>)>("clCEEGArtifacts_GetTimestampMilli");

  static final int Function(Pointer<Void>, int, Pointer<_NativeError>)
      _eegArtifactsGetArtifactByChannel = _capsuleClientLib.lookupFunction<
          Uint8 Function(Pointer<Void>, Int32, Pointer<_NativeError>),
          int Function(Pointer<Void>, int,
              Pointer<_NativeError>)>("clCEEGArtifacts_GetArtifactByChannel");

  static final double Function(Pointer<Void>, int, Pointer<_NativeError>)
      _eegArtifactsGetEEGQuality = _capsuleClientLib.lookupFunction<
          Float Function(Pointer<Void>, Int32, Pointer<_NativeError>),
          double Function(Pointer<Void>, int,
              Pointer<_NativeError>)>("clCEEGArtifacts_GetEEGQuality");

  static final int Function(Pointer<Void>, Pointer<_NativeError>)
      _psdDataGetTimestampMilli = _capsuleClientLib.lookupFunction<
          Uint64 Function(Pointer<Void>, Pointer<_NativeError>),
          int Function(Pointer<Void>,
              Pointer<_NativeError>)>("clCPSDData_GetTimestampMilli");

  static final int Function(Pointer<Void>, Pointer<_NativeError>)
      _psdDataGetChannelsCount = _capsuleClientLib.lookupFunction<
          Int32 Function(Pointer<Void>, Pointer<_NativeError>),
          int Function(Pointer<Void>,
              Pointer<_NativeError>)>("clCPSDData_GetChannelsCount");

  static final int Function(Pointer<Void>, Pointer<_NativeError>)
      _psdDataGetFrequenciesCount = _capsuleClientLib.lookupFunction<
          Int32 Function(Pointer<Void>, Pointer<_NativeError>),
          int Function(Pointer<Void>,
              Pointer<_NativeError>)>("clCPSDData_GetFrequenciesCount");

  static final double Function(Pointer<Void>, int, Pointer<_NativeError>)
      _psdDataGetFrequency = _capsuleClientLib.lookupFunction<
          Double Function(Pointer<Void>, Int32, Pointer<_NativeError>),
          double Function(Pointer<Void>, int,
              Pointer<_NativeError>)>("clCPSDData_GetFrequency");

  static final double Function(Pointer<Void>, int, int, Pointer<_NativeError>)
      _psdDataGetPSD = _capsuleClientLib.lookupFunction<
          Float Function(Pointer<Void>, Int32, Int32, Pointer<_NativeError>),
          double Function(Pointer<Void>, int, int,
              Pointer<_NativeError>)>("clCPSDData_GetPSD");

  static final double Function(Pointer<Void>, int, Pointer<_NativeError>)
      _psdDataGetBandUpper = _capsuleClientLib.lookupFunction<
          Float Function(Pointer<Void>, Int32, Pointer<_NativeError>),
          double Function(Pointer<Void>, int,
              Pointer<_NativeError>)>("clCPSDData_GetBandUpper");

  static final double Function(Pointer<Void>, int, Pointer<_NativeError>)
      _psdDataGetBandLower = _capsuleClientLib.lookupFunction<
          Float Function(Pointer<Void>, Int32, Pointer<_NativeError>),
          double Function(Pointer<Void>, int,
              Pointer<_NativeError>)>("clCPSDData_GetBandLower");

  static final bool Function(Pointer<Void>, Pointer<_NativeError>)
      _psdDataHasIndividualAlpha = _capsuleClientLib.lookupFunction<
          Bool Function(Pointer<Void>, Pointer<_NativeError>),
          bool Function(Pointer<Void>,
              Pointer<_NativeError>)>("clCPSDData_HasIndividualAlpha");

  static final double Function(Pointer<Void>, Pointer<_NativeError>)
      _psdDataGetIndividualAlphaUpper = _capsuleClientLib.lookupFunction<
          Float Function(Pointer<Void>, Pointer<_NativeError>),
          double Function(Pointer<Void>,
              Pointer<_NativeError>)>("clCPSDData_GetIndividualAlphaUpper");

  static final double Function(Pointer<Void>, Pointer<_NativeError>)
      _psdDataGetIndividualAlphaLower = _capsuleClientLib.lookupFunction<
          Float Function(Pointer<Void>, Pointer<_NativeError>),
          double Function(Pointer<Void>,
              Pointer<_NativeError>)>("clCPSDData_GetIndividualAlphaLower");

  static final bool Function(Pointer<Void>, Pointer<_NativeError>)
      _psdDataHasIndividualBeta = _capsuleClientLib.lookupFunction<
          Bool Function(Pointer<Void>, Pointer<_NativeError>),
          bool Function(Pointer<Void>,
              Pointer<_NativeError>)>("clCPSDData_HasIndividualBeta");

  static final double Function(Pointer<Void>, Pointer<_NativeError>)
      _psdDataGetIndividualBetaUpper = _capsuleClientLib.lookupFunction<
          Float Function(Pointer<Void>, Pointer<_NativeError>),
          double Function(Pointer<Void>,
              Pointer<_NativeError>)>("clCPSDData_GetIndividualBetaUpper");

  static final double Function(Pointer<Void>, Pointer<_NativeError>)
      _psdDataGetIndividualBetaLower = _capsuleClientLib.lookupFunction<
          Float Function(Pointer<Void>, Pointer<_NativeError>),
          double Function(Pointer<Void>,
              Pointer<_NativeError>)>("clCPSDData_GetIndividualBetaLower");

  static final _DartCallback _setOnIndividualCalibrationStageFinishedHandler =
      _capsuleClientLib.lookupFunction<_NativeCallback, _DartCallback>(
          'clCNFBCalibrator_SetOnCalibrationStageFinishedEvent');

  static final _DartIndividualNFBChangedCallback
      _setOnIndividualCalibratedHandler = _capsuleClientLib.lookupFunction<
              _NativeIndividualNFBChangedCallback,
              _DartIndividualNFBChangedCallback>(
          'clCNFBCalibrator_SetOnCalibratedEvent');

  static final void Function(Pointer<Void>, int, Pointer<_NativeError>)
      _nfbCalibratorCalibrateNFB = _capsuleClientLib.lookupFunction<
              Void Function(Pointer<Void>, Int32, Pointer<_NativeError>),
              void Function(Pointer<Void>, int, Pointer<_NativeError>)>(
          "clCNFBCalibrator_CalibrateIndividualNFB");

  static final void Function(Pointer<Void>, Pointer<_NativeError>)
      _nfbCalibratorCalibrateNFBQuick = _capsuleClientLib.lookupFunction<
              Void Function(Pointer<Void>, Pointer<_NativeError>),
              void Function(Pointer<Void>, Pointer<_NativeError>)>(
          "clCNFBCalibrator_CalibrateIndividualNFBQuick");

  static final void Function(
          Pointer<Void>, Pointer<_IndividualNFBInfo>, Pointer<_NativeError>)
      _nfbCalibratorImportIndividualNFBData = _capsuleClientLib.lookupFunction<
              Void Function(Pointer<Void>, Pointer<_IndividualNFBInfo>,
                  Pointer<_NativeError>),
              void Function(Pointer<Void>, Pointer<_IndividualNFBInfo>,
                  Pointer<_NativeError>)>(
          "clCNFBCalibrator_ImportIndividualNFBData");

  static final void Function(
          Pointer<Void>, Pointer<_IndividualNFBInfo>, Pointer<_NativeError>)
      _nfbCalibratorGetIndividualNFBData = _capsuleClientLib.lookupFunction<
          Void Function(Pointer<Void>, Pointer<_IndividualNFBInfo>,
              Pointer<_NativeError>),
          void Function(Pointer<Void>, Pointer<_IndividualNFBInfo>,
              Pointer<_NativeError>)>("clCNFBCalibrator_GetIndividualNFB");

  static final bool Function(Pointer<Void>) _isNfbCalibrated =
      _capsuleClientLib.lookupFunction<Bool Function(Pointer<Void>),
          bool Function(Pointer<Void>)>("clCNFBCalibrator_IsCalibrated");

  static final bool Function(Pointer<Void>) _hasNfbCalibrationFailed =
      _capsuleClientLib.lookupFunction<
          Bool Function(Pointer<Void>),
          bool Function(
              Pointer<Void>)>("clCNFBCalibrator_HasCalibrationFailed");

  static final bool Function(Pointer<Void>) _isNfbCalibrationReady =
      _capsuleClientLib.lookupFunction<Bool Function(Pointer<Void>),
          bool Function(Pointer<Void>)>("clCNFBCalibrator_IsReady");

  static final Pointer<Void> Function(Pointer<Void>, Pointer<_NativeError>)
      _cardioCreate = _capsuleClientLib.lookupFunction<
          Pointer<Void> Function(Pointer<Void>, Pointer<_NativeError>),
          Pointer<Void> Function(
              Pointer<Void>, Pointer<_NativeError>)>("clCCardio_Create");

  static final Pointer<Void> Function(
          Pointer<Void>, Pointer<Void>, Pointer<_NativeError>)
      _cardioCreateCalibrated = _capsuleClientLib.lookupFunction<
          Pointer<Void> Function(
              Pointer<Void>, Pointer<Void>, Pointer<_NativeError>),
          Pointer<Void> Function(Pointer<Void>, Pointer<Void>,
              Pointer<_NativeError>)>("clCCardio_CreateCalibrated");

  static final _DartCardioDataCallback _setCardioIndexesEventHandler =
      _capsuleClientLib.lookupFunction<_NativeCardioDataCallback,
          _DartCardioDataCallback>("clCCardio_SetOnIndexesUpdateEvent");

  static final _DartCallbackWithError _setCardioCalibratedEventHandler =
      _capsuleClientLib.lookupFunction<_NativeCallbackWithError,
          _DartCallbackWithError>("clCCardio_SetOnCalibratedEvent");

  static final _DartPointerCallbackWithError _setCardioPPGDataEventHandler =
      _capsuleClientLib.lookupFunction<_NativePointerCallbackWithError,
          _DartPointerCallbackWithError>('clCCardio_SetOnPPGDataEvent');

  static final Pointer<Void> Function(Pointer<Void>, Pointer<_NativeError>)
      _memsCreate = _capsuleClientLib.lookupFunction<
          Pointer<Void> Function(Pointer<Void>, Pointer<_NativeError>),
          Pointer<Void> Function(
              Pointer<Void>, Pointer<_NativeError>)>("clCMEMS_Create");

  static final Pointer<Void> Function(
          Pointer<Void>, Pointer<Void>, Pointer<_NativeError>)
      _memsCreateCalibrated = _capsuleClientLib.lookupFunction<
          Pointer<Void> Function(
              Pointer<Void>, Pointer<Void>, Pointer<_NativeError>),
          Pointer<Void> Function(Pointer<Void>, Pointer<Void>,
              Pointer<_NativeError>)>("clCMEMS_CreateCalibrated");

  static final _DartPointerCallbackWithError _setMEMSEventHandler =
      _capsuleClientLib.lookupFunction<_NativePointerCallbackWithError,
              _DartPointerCallbackWithError>(
          "clCMEMS_SetOnMEMSTimedDataUpdateEvent");

  static final _DartPointerCallbackWithError _setMEMSDataEventHandler =
      _capsuleClientLib.lookupFunction<_NativePointerCallbackWithError,
              _DartPointerCallbackWithError>(
          'clCMEMS_SetOnMEMSTimedDataUpdateEvent');

  static final Pointer<Void> Function(Pointer<Void>, Pointer<_NativeError>)
      _emotionsCreate = _capsuleClientLib.lookupFunction<
          Pointer<Void> Function(Pointer<Void>, Pointer<_NativeError>),
          Pointer<Void> Function(
              Pointer<Void>, Pointer<_NativeError>)>("clCEmotions_Create");

  static final _DartEmotionsCallback _setEmotionalStatesEventHandler =
      _capsuleClientLib.lookupFunction<_NativeEmotionsCallback,
          _DartEmotionsCallback>("clCEmotions_SetOnEmotionalStatesUpdateEvent");

  static final _DartStringCallback _setEmotionsErrorHandler = _capsuleClientLib
      .lookupFunction<_NativeStringCallback, _DartStringCallback>(
          "clCEmotions_SetOnErrorEvent");

  static final Pointer<Void> Function(Pointer<Void>, Pointer<_NativeError>)
      _productivityCreate = _capsuleClientLib.lookupFunction<
          Pointer<Void> Function(Pointer<Void>, Pointer<_NativeError>),
          Pointer<Void> Function(
              Pointer<Void>, Pointer<_NativeError>)>("clCProductivity_Create");

  static final Pointer<Void> Function(
          Pointer<Void>, Pointer<_IndividualNFBInfo>, Pointer<_NativeError>)
      _productivityCreateWithIndividualData = _capsuleClientLib.lookupFunction<
              Pointer<Void> Function(Pointer<Void>, Pointer<_IndividualNFBInfo>,
                  Pointer<_NativeError>),
              Pointer<Void> Function(Pointer<Void>, Pointer<_IndividualNFBInfo>,
                  Pointer<_NativeError>)>(
          "clCProductivity_CreateWithIndividualData");

  static final Pointer<Void> Function(Pointer<Void>,
          Pointer<_NativeProductivityBaselines>, Pointer<_NativeError>)
      _productivityImportBaselines = _capsuleClientLib.lookupFunction<
          Pointer<Void> Function(Pointer<Void>,
              Pointer<_NativeProductivityBaselines>, Pointer<_NativeError>),
          Pointer<Void> Function(
              Pointer<Void>,
              Pointer<_NativeProductivityBaselines>,
              Pointer<_NativeError>)>("clCProductivity_ImportBaselines");

  static final Pointer<Void> Function(Pointer<Void>, Pointer<_NativeError>)
      _productivityResetAccumulatedFatigue = _capsuleClientLib.lookupFunction<
              Pointer<Void> Function(Pointer<Void>, Pointer<_NativeError>),
              Pointer<Void> Function(Pointer<Void>, Pointer<_NativeError>)>(
          "clCProductivity_ResetAccumulatedFatigue");

  static final Pointer<Void> Function(Pointer<Void>)
      _productivityStartBaselineCalibration = _capsuleClientLib.lookupFunction<
          Pointer<Void> Function(Pointer<Void>),
          Pointer<Void> Function(
              Pointer<Void>)>("clCProductivity_StartBaselineCalibration");

  static final _DartProductivityBaselinesCallback
      _setProductivityBaselinesHandler = _capsuleClientLib.lookupFunction<
              _NativeProductivityBaselinesCallback,
              _DartProductivityBaselinesCallback>(
          'clCProductivity_SetOnBaselineUpdateEvent');

  static final _DartMetricsChangedCallback _setProductivityMetricsHandler =
      _capsuleClientLib.lookupFunction<_NativeMetricsChangedCallback,
              _DartMetricsChangedCallback>(
          'clCProductivity_SetOnMetricsUpdateEvent');

  static final _DartProductivityIndexesChangedCallback
      _setProductivityIndexesHandler = _capsuleClientLib.lookupFunction<
              _NativeProductivityIndexesChangedCallback,
              _DartProductivityIndexesChangedCallback>(
          'clCProductivity_SetOnIndexesUpdateEvent');

  static final _DartFloatCallback _setProductivityCalibrationProgressHandler =
      _capsuleClientLib
          .lookupFunction<_NativeFloatCallback, _DartFloatCallback>(
              'clCProductivity_SetOnCalibrationProgressUpdateEvent');

  static final _DartCallback _setProductivityIndividualNFBUpdateHandler =
      _capsuleClientLib.lookupFunction<_NativeCallback, _DartCallback>(
          'clCProductivity_SetOnIndividualNFBUpdateEvent');

  static final Pointer<Void> Function(Pointer<Void>) _nfbCalibratorCreate =
      _capsuleClientLib.lookupFunction<
          Pointer<Void> Function(Pointer<Void>),
          Pointer<Void> Function(
              Pointer<Void>)>("clCNFBCalibrator_CreateOrGet");

  static final Pointer<Void> Function(Pointer<Void>, Pointer<_NativeError>)
      _nfbCreate = _capsuleClientLib.lookupFunction<
          Pointer<Void> Function(Pointer<Void>, Pointer<_NativeError>),
          Pointer<Void> Function(
              Pointer<Void>, Pointer<_NativeError>)>("clCNFB_Create");

  static final Pointer<Void> Function(
          Pointer<Void>, Pointer<Void>, Pointer<_NativeError>)
      _nfbCreateCalibrated = _capsuleClientLib.lookupFunction<
          Pointer<Void> Function(
              Pointer<Void>, Pointer<Void>, Pointer<_NativeError>),
          Pointer<Void> Function(Pointer<Void>, Pointer<Void>,
              Pointer<_NativeError>)>("clCNFB_CreateCalibrated");

  static final _DartUserStateChangedCallback
      _setNFBUserStateChangedEventHandler = _capsuleClientLib.lookupFunction<
          _NativeUserStateChangedCallback,
          _DartUserStateChangedCallback>('clCNFB_SetOnUserStateChangedEvent');

  static final _DartStringCallback _setNFBErrorEventHandler = _capsuleClientLib
      .lookupFunction<_NativeStringCallback, _DartStringCallback>(
          'clCNFB_SetOnErrorEvent');

  static final Pointer<Void> Function(Pointer<Void>, Pointer<_NativeError>)
      _physiologicalStatesCreate = _capsuleClientLib.lookupFunction<
          Pointer<Void> Function(Pointer<Void>, Pointer<_NativeError>),
          Pointer<Void> Function(Pointer<Void>,
              Pointer<_NativeError>)>("clCPhysiologicalStates_Create");

  static final Pointer<Void> Function(Pointer<Void>,
          Pointer<_NativePhysiologicalBaselines>, Pointer<_NativeError>)
      _physiologicalStatesImportBaselines = _capsuleClientLib.lookupFunction<
          Pointer<Void> Function(Pointer<Void>,
              Pointer<_NativePhysiologicalBaselines>, Pointer<_NativeError>),
          Pointer<Void> Function(
              Pointer<Void>,
              Pointer<_NativePhysiologicalBaselines>,
              Pointer<_NativeError>)>("clCPhysiologicalStates_ImportBaselines");

  static final Pointer<Void> Function(Pointer<Void>)
      _physiologicalStatesStartBaselineCalibration =
      _capsuleClientLib.lookupFunction<Pointer<Void> Function(Pointer<Void>),
              Pointer<Void> Function(Pointer<Void>)>(
          "clCPhysiologicalStates_StartBaselineCalibration");

  static final _DartPhysiologicalStatesCallback
      _setPhysiologicalStatesUpdateHandler = _capsuleClientLib.lookupFunction<
              _NativePhysiologicalStatesCallback,
              _DartPhysiologicalStatesCallback>(
          'clCPhysiologicalStates_SetOnStatesUpdateEvent');

  static final _DartPhysiologicalBaselinesCallback
      _setPhysiologicalBaselinesHandler = _capsuleClientLib.lookupFunction<
              _NativePhysiologicalBaselinesCallback,
              _DartPhysiologicalBaselinesCallback>(
          'clCPhysiologicalStates_SetOnCalibratedEvent');

  static final _DartFloatCallbackWithError
      _setPhysiologicalStatesCalibrationProgressHandler =
      _capsuleClientLib.lookupFunction<_NativeFloatCallbackWithError,
              _DartFloatCallbackWithError>(
          'clCPhysiologicalStates_SetOnCalibrationProgressUpdateEvent');

  static final _DartCallbackWithError
      _setPhysiologicalStatesIndividualNFBUpdateHandler = _capsuleClientLib
          .lookupFunction<_NativeCallbackWithError, _DartCallbackWithError>(
              'clCPhysiologicalStates_SetOnIndividualNFBUpdateEvent');
}
