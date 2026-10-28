import contextlib
import json
import os
import signal
import socket
import subprocess
import threading
import time
import tomllib
from pathlib import Path


def load_config(path):
    path = Path(path).resolve()
    with path.open("rb") as file:
        config = tomllib.load(file)
    services = config.get("services", {})
    if not services:
        raise ValueError("Define al menos un servicio en forge.toml.")
    ports = set()
    for name, service in services.items():
        if not name.replace("-", "").replace("_", "").isalnum():
            raise ValueError("Nombre de servicio inválido.")
        command = service.get("command")
        if (
            not isinstance(command, list)
            or not command
            or not all(isinstance(x, str) and x for x in command)
        ):
            raise ValueError(f"{name}: command debe ser una lista de argumentos, sin shell.")
        service.setdefault("ports", [])
        service.setdefault("required_env", [])
        service.setdefault("depends_on", [])
        for port in service["ports"]:
            if not isinstance(port, int) or not 1 <= port <= 65535 or port in ports:
                raise ValueError("Puertos inválidos o repetidos en la configuración.")
            ports.add(port)
        if not all(isinstance(key, str) and key for key in service["required_env"]):
            raise ValueError("required_env debe contener nombres de variables.")
        service["directory"] = (path.parent / service.get("cwd", ".")).resolve()
        if not service["directory"].is_dir():
            raise ValueError(f"{name}: el directorio de trabajo no existe.")
        if any(dependency not in services for dependency in service["depends_on"]):
            raise ValueError(f"{name}: dependencia desconocida.")
    order(services)
    return services


def order(services):
    visited, visiting, result = set(), set(), []

    def visit(name):
        if name in visiting:
            raise ValueError("Existe un ciclo entre servicios.")
        if name in visited:
            return
        visiting.add(name)
        for dependency in services[name].get("depends_on", []):
            visit(dependency)
        visiting.remove(name)
        visited.add(name)
        result.append(name)

    for name in services:
        visit(name)
    return result


def environment(root):
    result = dict(os.environ)
    path = Path(root) / ".env"
    if path.exists():
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            key, separator, value = line.partition("=")
            if not separator or not key.strip().replace("_", "").isalnum():
                raise ValueError("Formato .env inválido; se espera NOMBRE=valor.")
            result.setdefault(key.strip(), value.strip().strip("\"'"))
    return result


def listening(port):
    with socket.socket() as connection:
        connection.settimeout(0.15)
        return connection.connect_ex(("127.0.0.1", port)) == 0


def validate(services, env):
    problems = []
    for name, service in services.items():
        for key in service["required_env"]:
            if not env.get(key):
                problems.append(f"{name}: falta la variable {key}")
        for port in service["ports"]:
            if listening(port):
                problems.append(f"{name}: el puerto {port} ya está ocupado")
    return problems


@contextlib.contextmanager
def lock(root):
    file = open(Path(root) / "lock", "a+b")
    try:
        file.seek(0)
        file.write(b"0")
        file.flush()
        file.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(file.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        file.close()
        raise ValueError("Ya hay un supervisor activo en este proyecto.") from None
    try:
        yield
    finally:
        file.close()


def collect(process, path):
    with process.stdout:
        while data := process.stdout.readline(65536):
            if path.exists() and path.stat().st_size > 5 * 1024**2:
                os.replace(path, path.with_suffix(".previous.log"))
            with path.open("ab") as file:
                file.write(data)


def stop(process):
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    else:
        os.killpg(process.pid, signal.SIGTERM)
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        if os.name != "nt":
            os.killpg(process.pid, signal.SIGKILL)
        process.kill()
        process.wait(timeout=5)


def supervise(config_path):
    config_path = Path(config_path).resolve()
    services = load_config(config_path)
    env = environment(config_path.parent)
    problems = validate(services, env)
    if problems:
        raise ValueError("\n".join(problems))
    state = config_path.parent / ".forge"
    state.mkdir(exist_ok=True)
    processes = {}
    threads = []
    with lock(state):
        (state / "stop").unlink(missing_ok=True)
        try:
            for name in order(services):
                service = services[name]
                kwargs = (
                    {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
                    if os.name == "nt"
                    else {"start_new_session": True}
                )
                process = subprocess.Popen(
                    service["command"],
                    cwd=service["directory"],
                    env=env,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    **kwargs,
                )
                processes[name] = process
                thread = threading.Thread(
                    target=collect, args=(process, state / (name + ".log")), daemon=True
                )
                thread.start()
                threads.append(thread)
                deadline = time.monotonic() + 30
                while service["ports"] and not all(listening(port) for port in service["ports"]):
                    if process.poll() is not None or time.monotonic() > deadline:
                        raise ValueError(f"{name}: no inició correctamente; revisa sus logs.")
                    time.sleep(0.1)
                print(f"[running] {name} / PID {process.pid}", flush=True)
            print(
                "Ctrl+C para detener. También puedes usar forge down desde otra terminal.",
                flush=True,
            )
            while not (state / "stop").exists():
                summary = {
                    "heartbeat": time.time(),
                    "services": {
                        name: {"pid": process.pid, "returncode": process.poll()}
                        for name, process in processes.items()
                    },
                }
                temporary = state / "state.tmp"
                temporary.write_text(json.dumps(summary), encoding="utf-8")
                os.replace(temporary, state / "state.json")
                dead = [name for name, process in processes.items() if process.poll() is not None]
                if dead:
                    raise ValueError("Servicios terminados: " + ", ".join(dead))
                time.sleep(0.3)
        except KeyboardInterrupt:
            pass
        finally:
            for process in reversed(list(processes.values())):
                stop(process)
            for thread in threads:
                thread.join(timeout=2)
            (state / "state.json").unlink(missing_ok=True)
            (state / "stop").unlink(missing_ok=True)
