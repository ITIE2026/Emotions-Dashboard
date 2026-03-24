// Copyright. 2019 - 2024 PSBD. All rights reserved.

using System;
using System.Threading;
using Capsule;
using Capsule.Utility;
using static Capsule.Productivity;

namespace CapsuleClientSharpExample
{
    internal static class Program
    {
        private static Calibrator? _calibrator;
        private static DeviceLocator? _locator;
        private static Device? _device;

        private static Nfb? _nfb;
        private static Productivity? _productivity;
        private static Cardio? _cardio;
        private static MEMS? _mems;
        private static PhysiologicalStates? _ps;
        private static Emotions? _emotions;

        private static bool StopRequested { get; set; }

        private static void OnMEMSData(MEMS mems, MEMS.MEMSData data)
        {
            Console.WriteLine($"MEMS: {data.Accelerometer} {data.Gyroscope}");
        }
        private static void OnPPGData(Cardio cardio, Cardio.PPGData data)
        {
            Console.WriteLine($"PPG: {data.Samples}");
        }
        private static void OnBatteryChargeUpdate(Device device, byte charge)
        {
            Console.WriteLine($"Battery charge: {(int)charge}");
        }
        private static void OnUpdateUserState(Nfb nfb, Nfb.UserState userState)
        {
            Console.WriteLine($"NFB update state: alpha = {userState.Alpha}, beta = {userState.Beta}, theta = {userState.Theta}");
        }
        private static void OnNFBError(Nfb nfb, string error)
        {
            Console.WriteLine($"NFB error {error}");
        }
        private static void OnProductivityBaselineUpdate(Productivity productivity, Baselines baselines)
        {
            Console.WriteLine($"Productivity baselines update: " +
                $"\nTimestamp: {baselines.Timestamp}" +
                $"\nGravity: {baselines.Gravity}" +
                $"\nProductivity: {baselines.Productivity}" +
                $"\nFatigue: {baselines.Fatigue}" +
                $"\nReverse Fatigue: {baselines.ReverseFatigue}" +
                $"\nRelaxation: {baselines.Relaxation}" +
                $"\nConcentration: {baselines.Concentration}");
        }
        private static void OnProductivityIndexesUpdate(Productivity productivity, Indexes indexes)
        {
            Console.WriteLine($"Productivity indexes update: Stress: {indexes.Stress} Relaxation: {indexes.Relaxation}");
        }
        private static void OnProductivityCalibrationProgress(Productivity productivity, float progress)
        {
            Console.WriteLine($"Productivity baseline calibration progress: {progress}");
        }
        private static void OnProductivityIndividualNFBUpdate(Productivity productivity)
        {
            Console.WriteLine($"Productivity individual nfb data has been updated");
        }
        private static void OnCardioIndexesUpdate(Cardio cardio, Cardio.CardioData data)
        {
            Console.WriteLine($"Cardio indexes update: (has artifacts: {data.Artifacted})" +
                $"\nKaplan's index: {data.KaplanIndex}" +
                $"\nHR: {data.HeartRate}" +
                $"\nStress index: {data.StressIndex}" +
                $"\nSkin contact: {data.SkinContact}" +
                $"\nMotion artifacts: {data.MotionArtifacts}" +
                $"\nMetrics available: {data.MetricsAvailable}");
        }
        
        private static void OnPhysiologicalStatesCalibrated(PhysiologicalStates ps, PhysiologicalStates.PhysiologicalStatesBaselines baselines)
        {
            Console.WriteLine($"Physiological states baselines calibrated:" +
                $"\ntTimestamp: {baselines.Timestamp}" +
                $"\nAlpha: {baselines.Alpha}" +
                $"\nBeta: {baselines.Beta}" +
                $"\nConcentration: {baselines.Concentration}" +
                $"\nAlpha gravity: {baselines.AlphaGravity}" +
                $"\nBeta gravity: {baselines.BetaGravity}");
        }
        private static void OnPhysiologicalStatesUpdate(PhysiologicalStates ps, PhysiologicalStates.PhysiologicalStatesValue value)
        {
            Console.WriteLine($"Physiological states update:" +
                $"\ntTimestamp: {value.Timestamp}" +
                $"\nRelaxation: {value.Relaxation}" +
                $"\nFatigue: {value.Fatigue}" +
                $"\nNone: {value.None}" +
                $"\nConcentration: {value.Concentration}" +
                $"\nInvolvement: {value.Involvement}" +
                $"\nStress: {value.Stress}" +
                $"\nNfb Artifacts: {value.NfbArtifacts}" +
                $"\nCardio Artifacts: {value.CardioArtifacts}");
        }
        private static void OnPhysiologicalStatesIndividualNFBUpdate(PhysiologicalStates ps)
        {
            Console.WriteLine($"Physiological states individual nfb data has been updated");
        }
        private static void OnEmotionalStatesUpdate(Emotions emotions, Emotions.EmotionalStates states)
        {
            Console.WriteLine($"Emotional states update: " +
                $"\nAttention: {states.Attention}" +
                $"\nRelaxation: {states.Relaxation}" +
                $"\nCognitiveLoad: {states.CognitiveLoad}" +
                $"\nCognitiveControl: {states.CognitiveControl}" +
                $"\nSelfControl: {states.SelfControl}");
        }
        private static void OnCalibrated(Calibrator calibrator, Calibrator.IndividualNfbData data)
        {
            if (data.FailReason != Calibrator.FailReason.None)
            {
                Console.WriteLine($"Calibration failed");
                switch (data.FailReason)
                {
                    case Calibrator.FailReason.TooManyArtifacts: { Console.WriteLine($"Too many artifacts"); break; }
                    case Calibrator.FailReason.PeakIsABorder: { Console.WriteLine($"Alpha peak matches one of the alpha range borders"); break; }
                    default: { Console.WriteLine($"Reason unknown"); break; }
                };
            }
            Console.WriteLine($"IAF: {data.IndividualFrequency}");
            _productivity!.StartBaselineCalibration();
        }
        private static void OnDeviceError(Device device, string error)
        {
            Console.WriteLine($"Device error: {error}");
        }
        private static void OnConnectionStatusChanged(Device device, Device.ConnectionStatus state)
        {
            if (state != Device.ConnectionStatus.Connected || _device == null)
            {
                Console.WriteLine($"Device disconnected");
                StopRequested = true;
                return;
            }
            Console.WriteLine($"Device connected");

            string[] chNames = device.ChannelNames();
            foreach (string s in chNames)
            {
                Console.WriteLine($"Channel: {s}");
            }
            
            Console.WriteLine("EEG sample rate: {0}", device.EegSampleRate);
            Console.WriteLine("PPG sample rate: {0}", device.PpgSampleRate);
            Console.WriteLine("MEMS sample rate: {0}", device.MemsSampleRate);
            Console.WriteLine("PPG IR amplitude: {0}", device.PpgIrAmplitude);
            Console.WriteLine("PPG Red amplitude: {0}", device.PpgRedAmplitude);

            device.Start();
            _ps?.StartBaselineCalibration();
            
            Console.WriteLine($"Calibration started\nClose your eyes for 30 seconds");
            try
            {
                _calibrator?.CalibrateIndividualNfbQuick();
            }
            catch (CapsuleException e)
            {
                Console.WriteLine($"Failed to start individual nfb calibration: {e.Message}");
                StopRequested = true;
            }
        }
        private static void OnDeviceList(DeviceLocator locator, DeviceInfo[] devices, DeviceLocator.FailReason failReason)
        {
            if (_device != null)
            {
                return;
            }

            if (failReason != DeviceLocator.FailReason.Ok)
            {
                switch (failReason)
                {
                    case DeviceLocator.FailReason.BluetoothDisabled:
                        {
                            Console.WriteLine($"Bluetooth adapter not found or disabled");
                            break;
                        }
                    default:
                        {
                            Console.WriteLine($"Unknown error occurred");
                            break;
                        }
                }
                Console.WriteLine($"Exiting...");
                StopRequested = true;
                return;
            }

            if (devices.Length == 0)
            {
                Console.WriteLine("Empty device list. Exiting...");
                StopRequested = true;
                return;
            }
            
            Console.WriteLine($"Found {devices.Length} devices.");
            foreach (var d in devices)
            {
                Console.WriteLine($"\t{d.Description}");
            }

            _device = locator.CreateDevice(devices[0].Serial);
            if (_device == null)
            {
                Console.WriteLine("Failed to create device. Exiting...");
                StopRequested = true;
                return;
            }

            _device.OnBatteryChargeUpdateEvent = OnBatteryChargeUpdate;
            _device.OnConnectionStatusChangedEvent = OnConnectionStatusChanged;
            _device.OnErrorEvent = OnDeviceError;

            _calibrator = new Calibrator(_device)
            {
                OnCalibratedEvent = OnCalibrated
            };

            try
            {
                _nfb = new Nfb(_device)
                {
                    OnUserStateChangedEvent = OnUpdateUserState,
                    OnErrorEvent = OnNFBError
                };
            }
            catch (CapsuleException e)
            {
                Console.WriteLine($"Failed to create nfb module: {e.Message}");
                Console.WriteLine("Exiting...");
                StopRequested = true;
                return;
            }

            try
            {
                _cardio = new Cardio(_device)
                {
                    OnIndexesUpdateEvent = OnCardioIndexesUpdate,
                    OnPPGDataEvent = OnPPGData
                };
            }
            catch (CapsuleException e)
            {
                Console.WriteLine($"Failed to create cardio module: {e.Message}");
                if (e.Code != ErrorCode.ModuleIsNotSupported) {
                    Console.WriteLine("Exiting...");
                    StopRequested = true;
                    return;
                }
            }

            try
            {
                _mems = new MEMS(_device)
                {
                    OnMEMSDataEvent = OnMEMSData
                };
            }
            catch (CapsuleException e)
            {
                Console.WriteLine($"Failed to create mems module: {e.Message}");
                if (e.Code != ErrorCode.ModuleIsNotSupported)
                {
                    Console.WriteLine("Exiting...");
                    StopRequested = true;
                    return;
                }
            }

            try
            {
                _productivity = new Productivity(_device)
                {
                    OnBaselineUpdateEvent = OnProductivityBaselineUpdate,
                    OnIndexesEvent = OnProductivityIndexesUpdate,
                    OnCalibrationProgressUpdateEvent = OnProductivityCalibrationProgress,
                    OnIndividualNFBUpdateEvent = OnProductivityIndividualNFBUpdate
                };
            }
            catch (CapsuleException e)
            {
                Console.WriteLine($"Failed to create productivity module: {e.Message}");
                Console.WriteLine("Exiting...");
                StopRequested = true;
                return;
            }

            try
            {
                _ps = new PhysiologicalStates(_device)
                {
                    OnPhysiologicalStatesCalibratedEvent = OnPhysiologicalStatesCalibrated,
                    OnPhysiologicalStatesUpdateEvent = OnPhysiologicalStatesUpdate,
                    OnIndividualNFBUpdateEvent = OnPhysiologicalStatesIndividualNFBUpdate
                };
            }
            catch (CapsuleException e)
            {
                Console.WriteLine($"Failed to create physiological states module: {e.Message}");
                if (e.Code != ErrorCode.ModuleIsNotSupported)
                {
                    Console.WriteLine("Exiting...");
                    StopRequested = true;
                    return;
                }
            }

            try
            {
                _emotions = new Emotions(_device)
                {
                    OnEmotionalStatesUpdateEvent = OnEmotionalStatesUpdate
                };
            }
            catch (CapsuleException e)
            {
                Console.WriteLine($"Failed to create emotions module: {e.Message}");
                Console.WriteLine("Exiting...");
                StopRequested = true;
                return;
            }

            _device.Connect(true);
        }
        
        public static void Main(string[] args)
        {
            Console.CancelKeyPress += (sender, e) =>
            {
                Console.WriteLine("\nCtrl+C pressed. Exiting gracefully...");
                e.Cancel = true;
                StopRequested = true;
            };
            Console.WriteLine($"Capsule: {Capsule.Capsule.Version}");
            Capsule.Capsule.Level = Capsule.Capsule.LogLevel.Trace;

            _locator = new DeviceLocator(new DefaultHandlerAdapter())
            {
                OnDeviceListEvent = OnDeviceList
            };
            _locator.RequestDevices(DeviceType.Noise, 15);
            while (!StopRequested) {
                Thread.Sleep(40);
            }
        }
    }
}
