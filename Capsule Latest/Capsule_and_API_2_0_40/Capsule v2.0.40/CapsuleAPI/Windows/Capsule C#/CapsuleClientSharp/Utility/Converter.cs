// Copyright. 2019 - 2024 PSBD. All rights reserved.

using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using static Capsule.Device;

namespace Capsule.Utility
{
    internal static class Converter
    {
        internal static IDictionary<IntPtr, object> CallbacksToOwners = new ConcurrentDictionary<IntPtr, object>();

        internal static T GetObjectFromPtr<T>(IntPtr ptr)
        {
            return (T)CallbacksToOwners[ptr];
        }

        internal class DeviceInfoInternal
        {

            public static DeviceInfo ConvertDeviceInfo(IntPtr deviceInfoPtr)
            {
                return new DeviceInfo(
                    Marshal.PtrToStringAnsi(GetSerial(deviceInfoPtr)),
                    Marshal.PtrToStringAnsi(GetName(deviceInfoPtr)),
                    GetType(deviceInfoPtr)
                );
            }

            internal static DeviceInfo[] ConvertDeviceInfoList(IntPtr devicesPtr)
            {
                var error = Error.Default;
                int count = GetCount(devicesPtr, ref error);
                if (!error.Success) throw new CapsuleException(error);
                DeviceInfo[] devices = new DeviceInfo[count];
                for (int i = 0; i < count; i++)
                {
                    IntPtr deviceInfo = GetDeviceInfo(devicesPtr, i, ref error);
                    if (!error.Success) throw new CapsuleException(error);
                    devices[i] = ConvertDeviceInfo(deviceInfo);
                }

                return devices;
            }

            [DllImport(Device.LibraryName, EntryPoint = "clCDeviceInfoList_GetCount")]
            private static extern int GetCount(IntPtr devicesPtr, ref Error error);

            [DllImport(Device.LibraryName, EntryPoint = "clCDeviceInfoList_GetDeviceInfo")]
            private static extern IntPtr GetDeviceInfo(IntPtr devicesPtr, int index, ref Error error);

            [DllImport(Device.LibraryName, EntryPoint = "clCDeviceInfo_GetSerial")]
            private static extern IntPtr GetSerial(IntPtr deviceInfoPtr);

            [DllImport(Device.LibraryName, EntryPoint = "clCDeviceInfo_GetName")]
            private static extern IntPtr GetName(IntPtr deviceInfoPtr);

            [DllImport(Device.LibraryName, EntryPoint = "clCDeviceInfo_GetType")]
            private static extern DeviceType GetType(IntPtr deviceInfoPtr);
        }

        internal class ResistanceInternal
        {
            internal static Device.Resistance[] ConvertResistance(IntPtr resistancePtr)
            {
                var count = GetCount(resistancePtr);
                var resistances = new Device.Resistance[count];

                for (var i = 0; i < count; ++i)
                {
                    resistances[i] = new Device.Resistance(Marshal.PtrToStringAnsi(GetChannelName(resistancePtr, i)),
                        GetValue(resistancePtr, i));
                }

                return resistances;
            }

            [DllImport(Device.LibraryName, EntryPoint = "clCResistance_GetCount")]
            private static extern int GetCount(IntPtr resistancesPtr);

            [DllImport(Device.LibraryName, EntryPoint = "clCResistance_GetChannelName")]
            private static extern IntPtr GetChannelName(IntPtr resistancesPtr, int index);

            [DllImport(Device.LibraryName, EntryPoint = "clCResistance_GetValue")]
            private static extern float GetValue(IntPtr resistancesPtr, int index);
        }

        #region EegData

        internal class EegDataInternal
        {
            public static Device.EegData ConvertEegData(IntPtr dataPtr)
        {
            var error = Error.Default;
            var channelsCount = GetChannelsCount(dataPtr, ref error);
            if (!error.Success) throw new CapsuleException(error);
            var samplesCount = GetSamplesCount(dataPtr, ref error);
            if (!error.Success) throw new CapsuleException(error);

            var eegTimedData = new Device.EegData
            {
                RawSamples = new float[channelsCount, samplesCount],
                ProcessedSamples = new float[channelsCount, samplesCount],
                TimestampsMilli = new ulong[samplesCount]
            };

            for (var i = 0; i < channelsCount; ++i)
            {
                for (var j = 0; j < samplesCount; ++j)
                {
                    eegTimedData.RawSamples[i, j] = GetRawValue(dataPtr, i, j, ref error);
                    eegTimedData.ProcessedSamples[i, j] = GetProcessedValue(dataPtr, i, j, ref error);
                    if (!error.Success) throw new CapsuleException(error);
                }
            }

            for (var j = 0; j < samplesCount; ++j)
            {
                eegTimedData.TimestampsMilli[j] = GetTimestampMilli(dataPtr, j, ref error);
                if (!error.Success) throw new CapsuleException(error);
            }

            return eegTimedData;
        }

        [DllImport(Device.LibraryName, EntryPoint = "clCEEGTimedData_GetChannelsCount")]
        private static extern int GetChannelsCount(IntPtr eegTimedData, ref Error error);

        [DllImport(Device.LibraryName, EntryPoint = "clCEEGTimedData_GetSamplesCount")]
        private static extern int GetSamplesCount(IntPtr eegTimedData, ref Error error);

        [DllImport(Device.LibraryName, EntryPoint = "clCEEGTimedData_GetRawValue")]
        private static extern float GetRawValue(IntPtr eegTimedData, int channelIndex, int sampleIndex,
            ref Error error);

        [DllImport(Device.LibraryName, EntryPoint = "clCEEGTimedData_GetProcessedValue")]
        private static extern float GetProcessedValue(IntPtr eegTimedData, int channelIndex, int sampleIndex,
            ref Error error);

        [DllImport(Device.LibraryName, EntryPoint = "clCEEGTimedData_GetTimestampMilli")]
        private static extern ulong GetTimestampMilli(IntPtr eegTimedData, int index, ref Error error);
        }

        #endregion

        #region PPGData

        internal class PPGDataInternal
        {
            public static Cardio.PPGData ConvertPPGData(IntPtr dataPtr)
            {
                var sampleCount = GetCount(dataPtr);
                var ppgTimedData = new Cardio.PPGData
                {
                    Samples = new float[sampleCount],
                    TimestampMilli = new ulong[sampleCount]
                };

                for (var i = 0; i < sampleCount; ++i)
                {
                    ppgTimedData.Samples[i] = GetValue(dataPtr, i);
                    ppgTimedData.TimestampMilli[i] = GetTimestampMilli(dataPtr, i);
                }

                return ppgTimedData;
            }

            [DllImport(Device.LibraryName, EntryPoint = "clCPPGTimedData_GetCount")]
            private static extern int GetCount(IntPtr ppgTimedData);

            [DllImport(Device.LibraryName, EntryPoint = "clCPPGTimedData_GetValue")]
            private static extern float GetValue(IntPtr ppgTimedData, int index);

            [DllImport(Device.LibraryName, EntryPoint = "clCPPGTimedData_GetTimestampMilli")]
            private static extern ulong GetTimestampMilli(IntPtr ppgTimedData, int index);
        }

        #endregion

        #region MEMSData

        internal class MEMSDataIternal
        {
            internal static MEMS.MEMSData ConvertMEMSData(IntPtr dataPtr)
            {
                var samplesCount = GetCount(dataPtr);
                var memsTimedData = new MEMS.MEMSData
                {
                    Accelerometer = new Point3D[samplesCount],
                    Gyroscope = new Point3D[samplesCount],
                    TimestampMilli = new ulong[samplesCount]
                };

                for (var i = 0; i < samplesCount; ++i)
                {
                    memsTimedData.Accelerometer[i] = GetAccelerometer(dataPtr, i);
                    memsTimedData.Gyroscope[i] = GetGyroscope(dataPtr, i);
                    memsTimedData.TimestampMilli[i] = GetTimestampMilli(dataPtr, i);
                }

                return memsTimedData;
            }

            [DllImport(Device.LibraryName, EntryPoint = "clCMEMSTimedData_GetCount")]
            private static extern int GetCount(IntPtr memsTimedData);

            [DllImport(Device.LibraryName, EntryPoint = "clCMEMSTimedData_GetAccelerometer")]
            private static extern Device.Point3D GetAccelerometer(IntPtr memsTimedData, int index);

            [DllImport(Device.LibraryName, EntryPoint = "clCMEMSTimedData_GetGyroscope")]
            private static extern Device.Point3D GetGyroscope(IntPtr memsTimedData, int index);

            [DllImport(Device.LibraryName, EntryPoint = "clCMEMSTimedData_GetTimestampMilli")]
            private static extern ulong GetTimestampMilli(IntPtr memsTimedData, int index);
        }

        #endregion

        #region EegArtifacts

        internal class EegArtifactsInternal
        {
            public static Device.EegArtifacts ConvertEegArtifacts(IntPtr dataPtr)
            {
                var error = Error.Default;
                var channelsCount = GetChannelsCount(dataPtr, ref error);
                if (!error.Success) throw new CapsuleException(error);

                var eegArtifacts = new Device.EegArtifacts
                {
                    Artifacts = new int[channelsCount],
                    EegQuality = new float[channelsCount]
                };

                for (var i = 0; i < channelsCount; ++i)
                {
                    var artifact = GetArtifactByChannel(dataPtr, i, ref error);
                    if (error.Success)
                    {
                        eegArtifacts.Artifacts[i] = artifact;
                    }

                    var eegQuality = GetEegQuality(dataPtr, i, ref error);
                    if (error.Success)
                    {
                        eegArtifacts.EegQuality[i] = eegQuality;
                    }
                }

                return eegArtifacts;
            }

            [DllImport(Device.LibraryName, EntryPoint = "clCEEGArtifacts_GetTimestampMilli")]
            private static extern ulong GetTimestampMilli(IntPtr eegArtifacts, ref Error error);

            [DllImport(Device.LibraryName, EntryPoint = "clCEEGArtifacts_GetChannelsCount")]
            private static extern int GetChannelsCount(IntPtr eegArtifacts, ref Error error);

            [DllImport(Device.LibraryName, EntryPoint = "clCEEGArtifacts_GetArtifactByChannel")]
            private static extern int GetArtifactByChannel(IntPtr eegArtifacts, int channelIndex, ref Error error);

            [DllImport(Device.LibraryName, EntryPoint = "clCEEGArtifacts_GetEEGQuality")]
            private static extern float GetEegQuality(IntPtr eegArtifacts, int channelIndex, ref Error error);
        }

        #endregion

        #region PsdData

        internal class PsdDataInternal
        {
            private enum PsdDataBand
            {
                Delta,
                Theta,
                Alpha,
                Smr,
                Beta
            }

            private static void CheckError(ref Error error) {
                if (!error.Success) throw new CapsuleException(error);
            }

            public static Device.PsdData ConvertPsdData(IntPtr dataPtr)
            {
                var error = Error.Default;
                var channelsCount = GetChannelsCount(dataPtr, ref error);
                CheckError(ref error);
                var frequenciesCount = GetFrequenciesCount(dataPtr, ref error);
                CheckError(ref error);

                var psdData = new Device.PsdData
                {
                    TimestampMilli = GetTimestampMilli(dataPtr, ref error),
                    Frequencies = new double[frequenciesCount],
                    Psd = new double[channelsCount, frequenciesCount],
                    Bands = new Bands()
                };
                CheckError(ref error);

                if (HasIndividualAlpha(dataPtr, ref error))
                {
                    CheckError(ref error);
                    psdData.IndividualAlpha = new HzRange(GetIndividualAlphaLower(dataPtr, ref error),
                        GetIndividualAlphaUpper(dataPtr, ref error));
                    CheckError(ref error);
                }

                if (HasIndividualBeta(dataPtr, ref error))
                {
                    CheckError(ref error);
                    psdData.IndividualBeta = new HzRange(GetIndividualBetaLower(dataPtr, ref error),
                        GetIndividualBetaUpper(dataPtr, ref error));
                    CheckError(ref error);
                }

                for (var j = 0; j < frequenciesCount; ++j)
                {
                    psdData.Frequencies[j] = GetFrequency(dataPtr, j, ref error);
                    CheckError(ref error);
                    psdData.Bands.Delta.Lower = GetBandLower(dataPtr, PsdDataBand.Delta, ref error);
                    CheckError(ref error);
                    psdData.Bands.Delta.Upper = GetBandUpper(dataPtr, PsdDataBand.Delta, ref error);
                    CheckError(ref error);

                    psdData.Bands.Theta.Lower = GetBandLower(dataPtr, PsdDataBand.Theta, ref error);
                    CheckError(ref error);
                    psdData.Bands.Theta.Upper = GetBandUpper(dataPtr, PsdDataBand.Theta, ref error);
                    CheckError(ref error);

                    psdData.Bands.Alpha.Lower = GetBandLower(dataPtr, PsdDataBand.Alpha, ref error);
                    CheckError(ref error);
                    psdData.Bands.Alpha.Upper = GetBandUpper(dataPtr, PsdDataBand.Alpha, ref error);
                    CheckError(ref error);

                    psdData.Bands.Smr.Lower = GetBandLower(dataPtr, PsdDataBand.Smr, ref error);
                    CheckError(ref error);
                    psdData.Bands.Smr.Upper = GetBandUpper(dataPtr, PsdDataBand.Smr, ref error);
                    CheckError(ref error);

                    psdData.Bands.Beta.Lower = GetBandLower(dataPtr, PsdDataBand.Beta, ref error);
                    CheckError(ref error);
                    psdData.Bands.Beta.Upper = GetBandUpper(dataPtr, PsdDataBand.Beta, ref error);
                    CheckError(ref error);
                    for (var i = 0; i < channelsCount; ++i)
                    {
                        psdData.Psd[i, j] = GetPsd(dataPtr, i, j, ref error);
                        CheckError(ref error);
                    }
                }

                return psdData;
            }

            [DllImport(Device.LibraryName, EntryPoint = "clCPSDData_GetTimestampMilli")]
            private static extern ulong GetTimestampMilli(IntPtr psdData, ref Error error);

            [DllImport(Device.LibraryName, EntryPoint = "clCPSDData_GetFrequenciesCount")]
            private static extern int GetFrequenciesCount(IntPtr psdData, ref Error error);

            [DllImport(Device.LibraryName, EntryPoint = "clCPSDData_GetChannelsCount")]
            private static extern int GetChannelsCount(IntPtr psdData, ref Error error);

            [DllImport(Device.LibraryName, EntryPoint = "clCPSDData_GetFrequency")]
            private static extern double GetFrequency(IntPtr psdData, int frequencyIndex, ref Error error);

            [DllImport(Device.LibraryName, EntryPoint = "clCPSDData_GetPSD")]
            private static extern double GetPsd(IntPtr psdData, int channelIndex, int frequencyIndex, ref Error error);

            [DllImport(Device.LibraryName, EntryPoint = "clCPSDData_GetBandUpper")]
            private static extern float GetBandUpper(IntPtr psdData, PsdDataBand band, ref Error error);

            [DllImport(Device.LibraryName, EntryPoint = "clCPSDData_GetBandLower")]
            private static extern float GetBandLower(IntPtr psdData, PsdDataBand band, ref Error error);

            [DllImport(Device.LibraryName, EntryPoint = "clCPSDData_HasIndividualAlpha")]
            private static extern bool HasIndividualAlpha(IntPtr psdData, ref Error error);

            [DllImport(Device.LibraryName, EntryPoint = "clCPSDData_GetIndividualAlphaLower")]
            private static extern float GetIndividualAlphaLower(IntPtr psdData, ref Error error);

            [DllImport(Device.LibraryName, EntryPoint = "clCPSDData_GetIndividualAlphaUpper")]
            private static extern float GetIndividualAlphaUpper(IntPtr psdData, ref Error error);

            [DllImport(Device.LibraryName, EntryPoint = "clCPSDData_HasIndividualBeta")]
            private static extern bool HasIndividualBeta(IntPtr psdData, ref Error error);

            [DllImport(Device.LibraryName, EntryPoint = "clCPSDData_GetIndividualBetaLower")]
            private static extern float GetIndividualBetaLower(IntPtr psdData, ref Error error);

            [DllImport(Device.LibraryName, EntryPoint = "clCPSDData_GetIndividualBetaUpper")]
            private static extern float GetIndividualBetaUpper(IntPtr psdData, ref Error error);
        }

        #endregion
    }
}
