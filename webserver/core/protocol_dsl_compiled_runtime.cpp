#include "protocol_dsl_compiled_runtime.h"

namespace openplc {

uint16_t crc16_modbus(const uint8_t* data, size_t len)
{
    uint16_t crc = 0xFFFF;
    for (size_t i = 0; i < len; i++)
    {
        crc ^= data[i];
        for (int b = 0; b < 8; b++)
        {
            if (crc & 0x0001)
            {
                crc = static_cast<uint16_t>((crc >> 1) ^ 0xA001);
            }
            else
            {
                crc = static_cast<uint16_t>(crc >> 1);
            }
        }
    }
    return crc;
}

uint8_t xor8(const uint8_t* data, size_t len)
{
    uint8_t value = 0;
    for (size_t i = 0; i < len; i++)
    {
        value ^= data[i];
    }
    return value;
}

uint8_t sum8(const uint8_t* data, size_t len)
{
    uint32_t sum = 0;
    for (size_t i = 0; i < len; i++)
    {
        sum += data[i];
    }
    return static_cast<uint8_t>(sum & 0xFF);
}

std::vector<uint8_t> append_checksum(const std::vector<uint8_t>& payload, const std::string& algo)
{
    std::vector<uint8_t> out(payload);

    if (algo == "CRC16_MODBUS")
    {
        uint16_t crc = crc16_modbus(payload.data(), payload.size());
        out.push_back(static_cast<uint8_t>(crc & 0xFF));
        out.push_back(static_cast<uint8_t>((crc >> 8) & 0xFF));
    }
    else if (algo == "XOR8")
    {
        out.push_back(xor8(payload.data(), payload.size()));
    }
    else if (algo == "SUM8")
    {
        out.push_back(sum8(payload.data(), payload.size()));
    }

    return out;
}

} // namespace openplc
