import 'dart:io';
import 'dart:async';

import 'package:example/capsule_api.dart';

DeviceLocator? locator;
Device? device;
NFBCalibrator? calibrator;
NFBClassifier? nfb;
Cardio? cardio;
Productivity? productivity;
Emotions? emotions;
MEMS? mems;

Future<void> delay() async {
  await Future.delayed(Duration(milliseconds: 50));
}

void onProductivityProgress(double progress) {
  print("productivity calibration progress $progress");
}

void onProductivityIndividualInfoUpdated() {
  print("productivity got individual information about user");
}

void onProductivtyMetrics(ProductivityMetrics productivityMetrics) {
  print("productivity got metrics: ${productivityMetrics.timestampMilli}");
}

void onUpdateUserState(int timestampMilli, double delta, double theta,
    double alpha, double smr, double beta) {
  // Getting NFB user data
  // if artifacts or weak resistance on the electrodes are observed,
  // the data will not be changed
  print(
      "NFB update state: time = $timestampMilli, alpha = $alpha, beta = $beta, theta = $theta");
}

void onNFBErrorEvent(String error) {
  print("NFB error: $error");
}

void onIndividualNFBCalibrated(info) {}

void onConnected() {
  try {
    // Create Productivity metric - mat constants are better not to change yet (get Productivity events, Initialize Productivity events)
    var metrics = Productivity(device!);

    metrics.individualNFBUpdateHandler = onProductivityIndividualInfoUpdated;
    metrics.calibrationProgressHandler = onProductivityProgress;
    metrics.metricsHandler = onProductivtyMetrics;

    // Initialize Productivity
    productivity = metrics;
  } catch (e) {
    print("Error: $e");
  }
}

void onResistances(List<Resistance> resistances) {
  return;
  // Get total number of resistance channels.
  int count = resistances.length;
  print("Resistances: $count");
  for (int i = 0; i < count; ++i) {
    String channelName = resistances[i].channelName;
    double value = resistances[i].value;
    print("Channel name: $channelName, resistance $value");
  }
}

void onEEG(List<EEGSample> samples) {
  //print("EEG: ${samples.length}");
}

void onPPG(List<PPGSample> samples) {
  print("PPG: ${samples.length}");
}

void onMEMS(List<MEMSSample> samples) {
  print("MEMS: ${samples.length}");
}

void onPSD(PSDData psd) {
  print("PSD: ${psd.spectrum.length}");
}

void onEEGArtifacts(EEGArtifacts artifacts) {
  print("EEG artifacts: ${artifacts.artifacts.length}");
}

void onCardioCalibrated() {
  print("Cardio calibrated");
}

void onCardioIndexes(CardioData cardioData) {
  print("Cardio indexes: ${cardioData.hasArtifacts}");
}

void onEmotionsUpdated(int timestampMilli, double attention, double relaxation,
    double cognitiveLoad, double cognitiveControl, double selfControl) {
  print("Emotions update: $timestampMilli");
}

void onEmotionsError(String error) {
  print("Emotions error: $error");
}

void onConnectionStateChanged(DeviceConnectionState state) {
  // clC_SE_Connected
  if (state != DeviceConnectionState.connected) {
    print("Device disconnected: $state");
    return;
  }

  print("Device connected");
  deviceConnectionTime = s_time;
  //onConnected();
}

void onDeviceList(
    List<DeviceInfo> devices, DeviceLocatorFailReason failReason) {
  // device connected
  if (device != null) {
    return;
  }

  if (failReason != DeviceLocatorFailReason.ok) {
    print("Failed to locate devices: $failReason");
  }

  // number of detected devices = 0 -> start the search again
  if (devices.isEmpty) {
    print("Empty device list");
    locator!.requestDevices(DeviceType.Noise, 10);
    return;
  }

  // print information about all found devices
  int count = devices.length;
  print("Devices: $count");
  for (int i = 0; i < count; ++i) {
    DeviceInfo deviceDescriptor = devices[i];
    String deviceDescription =
        "Device ID: ${deviceDescriptor.id} Device Name: ${deviceDescriptor.name}";
    print(deviceDescription);
  }

  // select device and connect
  DeviceInfo deviceDescriptor = devices[0];
  String deviceID = deviceDescriptor.id;
  try {
    var d = locator!.lockDevice(deviceID);
    d.eegDataHandler = onEEG;
    d.psdDataHandler = onPSD;
    d.eegArtifactsHandler = onEEGArtifacts;
    d.resistancesHandler = onResistances;
    d.connectionStateHandler = onConnectionStateChanged;
    d.connect(false);
    device = d;
  } catch (e) {
    print("Error: $e");
  }
}

int s_time = 0;
int deviceConnectionTime = 0;

Future<void> example() async {
  // Getting the version of the library
  String version = Capsule.version;
  Capsule.logLevel = LogLevel.info;
  print("version of the library: $version");
  var loc = DeviceLocator();
  loc.devicesHandler = onDeviceList;
  loc.requestDevices(DeviceType.Noise, 15);
  locator = loc;

  int kMsSec = 1000;

  while (s_time < 720000) {
    // Update does all the work and must be called regularly to process events.
    loc.update();
    await delay();
    s_time += 50;

    if (device == null) {
      continue;
    }
    // The device transmits a raw signal to the capsule -
    // to convert it to alpha beta or theta rhythms - an nfb object is
    // needed
    if ((s_time == deviceConnectionTime + 3 * kMsSec) && (nfb == null)) {
      // Create NFB (get NFB events, Initialize NFB events)
      try {
        var nfbClassifier = NFBClassifier(device!);
        nfbClassifier.userStateHandler = onUpdateUserState;
        nfbClassifier.errorHandler = onNFBErrorEvent;
        nfb = nfbClassifier;
      } catch (e) {
        print("Error: $e");
      }
    }

    // Cardio module
    if ((s_time == deviceConnectionTime + 5 * kMsSec) && (cardio == null)) {
      // Create cardio
      try {
        var cardioClassifier = Cardio(device!);
        cardioClassifier.calibratedHandler = onCardioCalibrated;
        cardioClassifier.indexesHandler = onCardioIndexes;
        cardio = cardioClassifier;
        cardio.ppgDataHandler = onPPG;
      } catch (e) {
        print("Error: $e");
      }
    }

    // Emotions module
    if ((s_time == deviceConnectionTime + 7 * kMsSec) && (emotions == null)) {
      // Create emotions
      try {
        var emotionsClassifier = Emotions(device!);
        emotionsClassifier.emotionsHandler = onEmotionsUpdated;
        emotionsClassifier.errorHandler = onEmotionsError;
        emotions = emotionsClassifier;
      } catch (e) {
        print("Error: $e");
      }
    }

    if ((s_time == deviceConnectionTime + 9 * kMsSec) && (mems == null)) {
      // Create mems
      try {
        var memsClassifier = MEMS(device!);
        mems = memsClassifier;
        mems.memsDataHandler = onMEMS;
      } catch (e) {
        print("Error: $e");
      }
    }

    // Productivity metrics is an algorithm that uses custom rhythms
    // and an IAPF and other indicators to calculate the productivity score
    if ((s_time == deviceConnectionTime + 11 * kMsSec) &&
        (productivity == null)) {
      var nfbCalibrator = NFBCalibrator(device!);
      nfbCalibrator.calibratedHandler = onIndividualNFBCalibrated;
      // switch the device to receive a signal
      device!.start();
      calibrator = nfbCalibrator;
    }

    if (s_time == deviceConnectionTime + 80 * kMsSec) {
      device?.disconnect();
      productivity?.destroy();
      cardio?.destroy();
      nfb?.destroy();
      calibrator?.destroy();
      device?.destroy();
      locator?.destroy();

      calibrator = null;
      device = null;
      locator = null;
      productivity = null;
      cardio = null;
      nfb = null;
    }
    // in order to calculate individual characteristics,
    // it is necessary to take 4 measurements
    // closed eyes - open - closed - open each for 20 seconds
    if (s_time == deviceConnectionTime + 5 * kMsSec) {
      // closed eyes
      calibrator?.calibrateIndividualNFB(IndividualNFBCalibrationStage.stage1);
    }
    if (s_time == deviceConnectionTime + 27 * kMsSec) {
      // open eyes
      calibrator?.calibrateIndividualNFB(IndividualNFBCalibrationStage.stage2);
    }
    if (s_time == deviceConnectionTime + 49 * kMsSec) {
      // closed eyes
      calibrator?.calibrateIndividualNFB(IndividualNFBCalibrationStage.stage3);
    }
    if (s_time == deviceConnectionTime + 71 * kMsSec) {
      // open eyes
      calibrator?.calibrateIndividualNFB(IndividualNFBCalibrationStage.stage4);
    }
  }
}

Future<void> main(List<String> arguments) async {
  try {
    await example();
  } catch (e, stacktrace) {
    print(e);
    print(stacktrace);
  }
  print('Press Enter for exit');
  stdin.readLineSync();
  exit(0);
}
