// Copyright. 2019 - 2024 PSBD. All rights reserved.

namespace Capsule
{
    /**
 * \brief Device info.
 *
 * Contains device information: name, id (serial number) and type
 */
    public readonly struct DeviceInfo
    {
        internal DeviceInfo(string serial, string name, DeviceType type)
        {
            Serial = serial;
            Name = name;
            Type = type;
        }

        public readonly string Serial;
        public readonly string Name;
        public readonly DeviceType Type;

        public readonly string Description
        {
            get
            {
                var formatId = Serial.Length > 0 ? "ID" : "missing ID";
                return $"{Name} ({formatId})";
            }
        }
    }

    public enum DeviceType
    {
        Headband = 0,
        Buds = 1,
        Headphones = 2,
        Impulse = 3,
        Any = 4,
        BrainBit = 6,
        SinWave = 100,
        Noise = 101
    }
}