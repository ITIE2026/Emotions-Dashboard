// Copyright. 2019 - 2024 PSBD. All rights reserved.

using System.Runtime.InteropServices;
using static Capsule.Utility.Converter;

namespace Capsule.Utility
{
    /**
    * \brief Handler adapter for events.
    */
    public interface IHandlerAdapter
    {
        void Attach<T>(T obj, [Optional] object deviceObj);
        object Map(Handler<DeviceLocator> handler);
    }

    /**
     * \brief Default handler adapter.
     */
    public sealed class DefaultHandlerAdapter : IHandlerAdapter
    {
        public void Attach<T>(T obj, [Optional] object deviceObj)
        {
            switch (obj)
            {
                case DeviceLocator locator:
                {
                    locator.SetDeviceListHandler((ptr, dPtr, err) =>
                    {
                        var l = GetObjectFromPtr<DeviceLocator>(ptr);
                        l.OnDeviceListEvent?.Invoke(l, DeviceInfoInternal.ConvertDeviceInfoList(dPtr), err);
                    });
                    break;
                }
                case Device device:
                {
                    device.SetConnectionStatusChangedHandler((ptr, connected) =>
                    {
                        var d = GetObjectFromPtr<Device>(ptr);
                        d.OnConnectionStatusChangedEvent?.Invoke(d, connected);
                    });
                    device.SetResistanceUpdateHandler((ptr, resistance) =>
                    {
                        var d = GetObjectFromPtr<Device>(ptr);
                        d.OnResistanceUpdateEvent?.Invoke(d, ResistanceInternal.ConvertResistance(resistance));
                    });
                    device.SetModeSwitchedHandler((ptr, mode) =>
                    {
                        var d = GetObjectFromPtr<Device>(ptr);
                        d.OnModeSwitchedEvent?.Invoke(d, mode);
                    });
                    device.SetErrorHandler((ptr, error) => {
                        var d = GetObjectFromPtr<Device>(ptr);
                        d.OnErrorEvent?.Invoke(d, error);
                    });
                    device.SetEegDataHandler((ptr, eeg) => {
                        var d = GetObjectFromPtr<Device>(ptr);
                        try
                        {
                            d.EegDataCurrent = EegDataInternal.ConvertEegData(eeg);
                            d.OnEegDataEvent?.Invoke(d, d.EegDataCurrent);
                        }
                        catch (CapsuleException ex)
                        {
                            System.Diagnostics.Debug.WriteLine($"Failed to convert eeg data: {ex.Message}");
                        }
                    });
                    device.SetPsdDataHandler((ptr, psd) =>
                    {
                        var d = GetObjectFromPtr<Device>(ptr);
                        try
                        {
                            d.PsdDataCurrent = PsdDataInternal.ConvertPsdData(psd);
                            d.OnPsdDataEvent?.Invoke(d, d.PsdDataCurrent);
                        }
                        catch (CapsuleException ex)
                        {
                            System.Diagnostics.Debug.WriteLine($"Failed to convert psd data: {ex.Message}");
                        }
                    });
                    device.SetEegArtifactsHandler((ptr, eegArtifacts) =>
                    {
                        var d = GetObjectFromPtr<Device>(ptr);
                        try
                        {
                            d._EegArtifacts = EegArtifactsInternal.ConvertEegArtifacts(eegArtifacts);
                            d.OnEegArtifactsEvent?.Invoke(d, d._EegArtifacts);
                        }
                        catch (CapsuleException ex)
                        {
                            System.Diagnostics.Debug.WriteLine($"Failed to convert eeg artifacts: {ex.Message}");
                        }
                    });
                    device.SetBatteryChargeUpdateHandler((ptr, charge) =>
                    {
                        var d = GetObjectFromPtr<Device>(ptr);
                        d.OnBatteryChargeUpdateEvent?.Invoke(d, charge);
                    });
                    break;
                }
                case Nfb nfb:
                {
                    nfb.SetUserStateChangedHandler((ptr, state) =>
                    {
                        var c = GetObjectFromPtr<Nfb>(ptr);
                        c.OnUserStateChangedEvent?.Invoke(c, state);
                    });
                    nfb.SetErrorHandler((ptr, errorPtr) =>
                    {
                        var c = GetObjectFromPtr<Nfb>(ptr);
                        c.OnErrorEvent?.Invoke(c, errorPtr);
                    });
                    break;
                }
                case Calibrator calibrator:
                {
                    calibrator.SetIndividualNfbStageFinishedHandler(ptr =>
                    {
                        var c = GetObjectFromPtr<Calibrator>(ptr);
                        c.OnIndividualNfbStageFinishedEvent?.Invoke(c);
                    });
                    calibrator.SetCalibratedHandler((ptr, nfb) =>
                    {
                        var c = GetObjectFromPtr<Calibrator>(ptr);
                        c.OnCalibratedEvent?.Invoke(c, nfb);
                    });
                    break;
                }
                case Productivity productivity:
                {
                    productivity.SetBaselineUpdateHandler((ptr, baselines) =>
                    {
                        var c = GetObjectFromPtr<Productivity>(ptr);
                        c.OnBaselineUpdateEvent?.Invoke(c, baselines);
                    });
                    productivity.SetIndexesHandler((ptr, indexes) =>
                    {
                        var c = GetObjectFromPtr<Productivity>(ptr);
                        c.OnIndexesEvent?.Invoke(c, indexes);
                    });

                    productivity.SetMetricsUpdateHandler((ptr, metrics) =>
                    {
                        var c = GetObjectFromPtr<Productivity>(ptr);
                        c.OnMetricsUpdateEvent?.Invoke(c, new Productivity.Metrics(metrics));
                    });
                    productivity.SetCalibrationProgressUpdateHandler((ptr, values) =>
                    {
                        var c = GetObjectFromPtr<Productivity>(ptr);
                        c.OnCalibrationProgressUpdateEvent?.Invoke(c, values);
                    });
                    productivity.SetIndividualNFBUpdateHandler((ptr) =>
                    {
                        var c = GetObjectFromPtr<Productivity>(ptr);
                        c.OnIndividualNFBUpdateEvent?.Invoke(c);
                    });
                    break;
                }
                case Cardio cardio:
                {
                    Error error = new Error();
                    cardio.SetIndexesUpdateHandler((ptr, value) =>
                    {
                        var c = GetObjectFromPtr<Cardio>(ptr);
                        c.OnIndexesUpdateEvent?.Invoke(c, value);
                    }, ref error);
                    cardio.SetCalibratedHandler((ptr) =>
                    {
                        var c = GetObjectFromPtr<Cardio>(ptr);
                        c.OnCalibratedEvent?.Invoke(c);
                    }, ref error);
                    Device dv = (Device)deviceObj;
                    cardio.SetPPGDataHandler((ptr, ppg) => {
                        var c = GetObjectFromPtr<Cardio>(ptr);
                        c.PPGDataCurrent = PPGDataInternal.ConvertPPGData(ppg);
                        c.OnPPGDataEvent?.Invoke(c, c.PPGDataCurrent);
                    }, ref error);
                    break;
                }
                case Emotions emotions:
                {
                    emotions.SetErrorHandler((ptr, errorPtr) =>
                    {
                        var c = GetObjectFromPtr<Emotions>(ptr);
                        c.OnErrorEvent?.Invoke(c, errorPtr);
                    });
                    emotions.SetEmotionsStateDelegateFloatHandler((ptr, val) =>
                    {
                        var c = GetObjectFromPtr<Emotions>(ptr);
                        c.OnEmotionalStatesUpdateEvent?.Invoke(c, val);
                    });
                    break;
                }
                case PhysiologicalStates states:
                {
                    Error error = new Error();
                    states.SetPSCalibratedHandler((ptr, arg) =>
                    {
                        var c = GetObjectFromPtr<PhysiologicalStates>(ptr);
                        c.OnPhysiologicalStatesCalibratedEvent?.Invoke(c, arg);
                    }, ref error);
                    states.SetPSUpdateHandler((ptr, arg) =>
                    {
                        var c = GetObjectFromPtr<PhysiologicalStates>(ptr);
                        c.OnPhysiologicalStatesUpdateEvent?.Invoke(c, arg);
                    }, ref error);
                    states.SetPSCalibrationProgressUpdateHandler((ptr, arg) =>
                    {
                        var c = GetObjectFromPtr<PhysiologicalStates>(ptr);
                        c.OnCalibrationProgressUpdateEvent?.Invoke(c, arg);
                    }, ref error);
                    states.SetPSIndividualNFBUpdateHandler((ptr) =>
                    {
                        var c = GetObjectFromPtr<PhysiologicalStates>(ptr);
                        c.OnIndividualNFBUpdateEvent?.Invoke(c);
                    }, ref error);
                    break;
                }
                case MEMS MEMSData:
                {
                    Error error = new Error();
                    MEMSData.SetMEMSDataHandler((ptr, MEMSData) =>
                    {
                        var m = GetObjectFromPtr<MEMS>(ptr);
                        m.MEMSDataCurrent = MEMSDataIternal.ConvertMEMSData(MEMSData);
                        m.OnMEMSDataEvent?.Invoke(m, m.MEMSDataCurrent);
                    }, ref error);
                    break;
                }
            }
        }

        public static IHandlerAdapter Adapter() => new DefaultHandlerAdapter();

        public object Map(Handler<DeviceLocator> handler)
        {
            HandlerCallback lambda = ptr =>
            {
                var c = GetObjectFromPtr<DeviceLocator>(ptr);
                handler(c);
            };
            return lambda;
        }
    }
}