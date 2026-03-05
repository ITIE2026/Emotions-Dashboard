import 'package:test/test.dart';
import 'package:example/capsule_api.dart';

bool isServerConnected = false;
void onConnected() {
  isServerConnected = true;
}

List<DeviceInfo>? devices;
void onDeviceList(List<DeviceInfo> availableDevices) {
  devices = availableDevices;
}

bool connectionState = false;
void onStateChange(int deviceConnection) {
  connectionState = (deviceConnection == 1);
}

bool isSessionStarted = false;
void onSessionStart() {
  isSessionStarted = true;
}

bool isSessionStopped = false;
void onSessionStop() {
  isSessionStopped = true;
}

DisconnectReason? disconnectReason;
void onDisconnect(DisconnectReason reason) {
  disconnectReason = reason;
}

Future<void> delay() async {
  await Future.delayed(Duration(milliseconds: 50));
}

Future<void> main() async {
  Client? client = Client();
  DeviceLocator? deviceLocator;
  Device? device;
  Session? session;

  group('Dart API Test', () {
    test('Connect to server', () {
      client.connectedHandler = onConnected;
      client.connect(address: "inproc://capsule");
      expect(client.connected, equals(true));
    });
    test('Сlient version test', () {
      String version = Client.getVersion();
      expect(version.isEmpty, equals(false));
    });
    test('Search for device test', () {
      deviceLocator = client.chooseDeviceType(DeviceType.Noise);
      deviceLocator!.devicesHandler = onDeviceList;
      deviceLocator!.requestDevices(60);
      expect(devices!.length, isNot(0));
    });
    test('Connect to device test', () {
      DeviceInfo deviceDescriptor = devices!.first;
      String deviceID = deviceDescriptor.id;
      device = deviceLocator!.lockDevice(deviceID);
      device!.connectionStateHandler = onStateChange;
      device!.connect();
      expect(connectionState, equals(true));
      expect(device!.connected, equals(true));
    });
    test('Get mode test', () {
      DeviceMode deviceMode = device!.deviceMode;
      expect(deviceMode, equals(DeviceMode.idle));
    });
    test('Start session test', () {
      int error = 1;
      Session session = client!.createSession(device!, error);
      expect(error, equals(0));
      session.sessionStartedHandler = onSessionStart;
      session.start();
      expect(isSessionStarted, equals(true));
      expect(session.active, equals(true));
    });
    test('Stop session test', () {
      session!.sessionStoppedHandler = onSessionStop;
      session.stop();
      expect(isSessionStopped, equals(true));
      expect(session.active, equals(false));
    });
    test('Disconnect device test', () {
      expect(device!.connected, equals(true));
      device!.disconnect();
      expect(device!.connected, equals(false));
    });
    test('Disconnect from server test', () {
      client.disconnectedEventHandler = onDisconnect;
      client.disconnect;
      expect(disconnectReason == null, equals(false));
      expect(disconnectReason, equals(DisconnectReason.userRequested));
    });
    client.destroy();
  });
}
