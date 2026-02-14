#include "protocol_dsl_runtime.h"
#include "protocol_dsl_compiled_runtime.h"

#include <cerrno>
#include <cstring>
#include <fcntl.h>
#include <netinet/in.h>
#include <sys/select.h>
#include <sys/socket.h>
#include <termios.h>
#include <unistd.h>
#include <arpa/inet.h>

namespace openplc {

static speed_t resolveBaud(int baud)
{
    switch (baud)
    {
        case 1200: return B1200;
        case 2400: return B2400;
        case 4800: return B4800;
        case 9600: return B9600;
        case 19200: return B19200;
        case 38400: return B38400;
        case 57600: return B57600;
        case 115200: return B115200;
        default: return B9600;
    }
}

bool ProtocolDslRuntime::verifyCrc16Modbus(const std::vector<uint8_t>& frame)
{
    if (frame.size() < 3) return false;

    const size_t data_size = frame.size() - 2;
    const uint16_t expected = crc16_modbus(frame.data(), data_size);
    const uint16_t received = static_cast<uint16_t>(frame[data_size]) |
                              (static_cast<uint16_t>(frame[data_size + 1]) << 8);
    return expected == received;
}

RuntimeCycleResult ProtocolDslRuntime::runCycleTcp(const std::vector<uint8_t>& tx,
                                                   const std::string& host,
                                                   uint16_t port,
                                                   int timeout_ms,
                                                   bool verify_crc16) const
{
    RuntimeCycleResult out;
    out.tx = tx;

    int sock = socket(AF_INET, SOCK_STREAM, 0);
    if (sock < 0)
    {
        out.comm_disconnected = true;
        out.comm_error = true;
        out.error_text = std::strerror(errno);
        return out;
    }

    struct timeval tv;
    tv.tv_sec = timeout_ms / 1000;
    tv.tv_usec = (timeout_ms % 1000) * 1000;
    setsockopt(sock, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof(tv));
    setsockopt(sock, SOL_SOCKET, SO_SNDTIMEO, &tv, sizeof(tv));

    struct sockaddr_in addr;
    std::memset(&addr, 0, sizeof(addr));
    addr.sin_family = AF_INET;
    addr.sin_port = htons(port);
    if (inet_pton(AF_INET, host.c_str(), &addr.sin_addr) <= 0)
    {
        close(sock);
        out.comm_disconnected = true;
        out.comm_error = true;
        out.error_text = "invalid host";
        return out;
    }

    if (connect(sock, reinterpret_cast<struct sockaddr*>(&addr), sizeof(addr)) != 0)
    {
        out.comm_disconnected = true;
        out.comm_error = true;
        out.error_text = std::strerror(errno);
        close(sock);
        return out;
    }

    ssize_t sent = send(sock, tx.data(), tx.size(), 0);
    if (sent < 0)
    {
        out.comm_error = true;
        out.error_text = std::strerror(errno);
        close(sock);
        return out;
    }

    uint8_t buff[4096];
    ssize_t recvd = recv(sock, buff, sizeof(buff), 0);
    if (recvd <= 0)
    {
        out.comm_error = true;
        out.error_text = (recvd == 0) ? "peer closed" : std::strerror(errno);
        close(sock);
        return out;
    }

    out.rx.assign(buff, buff + recvd);
    close(sock);

    if (verify_crc16 && !verifyCrc16Modbus(out.rx))
    {
        out.checksum_error = true;
        out.comm_error = true;
        out.error_text = "CRC16 mismatch";
    }

    return out;
}

RuntimeCycleResult ProtocolDslRuntime::runCycleRtu(const std::vector<uint8_t>& tx,
                                                   const std::string& serial_port,
                                                   int baud,
                                                   char parity,
                                                   int data_bits,
                                                   int stop_bits,
                                                   int timeout_ms,
                                                   bool verify_crc16) const
{
    RuntimeCycleResult out;
    out.tx = tx;

    int fd = open(serial_port.c_str(), O_RDWR | O_NOCTTY | O_SYNC);
    if (fd < 0)
    {
        out.comm_disconnected = true;
        out.comm_error = true;
        out.error_text = std::strerror(errno);
        return out;
    }

    struct termios tty;
    std::memset(&tty, 0, sizeof tty);
    if (tcgetattr(fd, &tty) != 0)
    {
        out.comm_error = true;
        out.error_text = std::strerror(errno);
        close(fd);
        return out;
    }

    cfsetospeed(&tty, resolveBaud(baud));
    cfsetispeed(&tty, resolveBaud(baud));

    tty.c_cflag |= (CLOCAL | CREAD);
    tty.c_cflag &= ~CSIZE;
    tty.c_cflag |= (data_bits == 7) ? CS7 : CS8;

    if (parity == 'E')
    {
        tty.c_cflag |= PARENB;
        tty.c_cflag &= ~PARODD;
    }
    else if (parity == 'O')
    {
        tty.c_cflag |= PARENB;
        tty.c_cflag |= PARODD;
    }
    else
    {
        tty.c_cflag &= ~PARENB;
    }

    if (stop_bits == 2) tty.c_cflag |= CSTOPB;
    else tty.c_cflag &= ~CSTOPB;

    tty.c_cc[VMIN] = 0;
    tty.c_cc[VTIME] = 0;

    if (tcsetattr(fd, TCSANOW, &tty) != 0)
    {
        out.comm_error = true;
        out.error_text = std::strerror(errno);
        close(fd);
        return out;
    }

    ssize_t sent = write(fd, tx.data(), tx.size());
    if (sent < 0)
    {
        out.comm_error = true;
        out.error_text = std::strerror(errno);
        close(fd);
        return out;
    }

    fd_set read_fds;
    FD_ZERO(&read_fds);
    FD_SET(fd, &read_fds);

    struct timeval tv;
    tv.tv_sec = timeout_ms / 1000;
    tv.tv_usec = (timeout_ms % 1000) * 1000;

    int sel = select(fd + 1, &read_fds, NULL, NULL, &tv);
    if (sel <= 0)
    {
        out.comm_error = true;
        out.error_text = (sel == 0) ? "timeout" : std::strerror(errno);
        close(fd);
        return out;
    }

    uint8_t buff[4096];
    ssize_t recvd = read(fd, buff, sizeof(buff));
    if (recvd <= 0)
    {
        out.comm_error = true;
        out.error_text = std::strerror(errno);
        close(fd);
        return out;
    }

    out.rx.assign(buff, buff + recvd);
    close(fd);

    if (verify_crc16 && !verifyCrc16Modbus(out.rx))
    {
        out.checksum_error = true;
        out.comm_error = true;
        out.error_text = "CRC16 mismatch";
    }

    return out;
}

} // namespace openplc
