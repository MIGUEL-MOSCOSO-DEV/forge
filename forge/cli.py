import argparse
import json
import sys
import time
from collections import deque
from pathlib import Path

from .supervisor import environment, load_config, supervise, validate


def main(argv=None):
    parser = argparse.ArgumentParser(description="Forge · procesos de desarrollo bajo tu control")
    parser.add_argument("--config", type=Path, default=Path("forge.toml"))
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("init", help="Crear un archivo de configuración vacío")
    commands.add_parser("check", help="Revisar puertos y variables, sin iniciar procesos")
    commands.add_parser("up", help="Iniciar y supervisar en primer plano")
    commands.add_parser("down", help="Solicitar el cierre del supervisor de este directorio")
    commands.add_parser("status", help="Estado del supervisor local")
    logs = commands.add_parser("logs", help="Mostrar las últimas líneas de un servicio")
    logs.add_argument("service")
    logs.add_argument("--lines", type=int, default=60)
    args = parser.parse_args(argv)
    state = args.config.resolve().parent / ".forge"
    try:
        if args.command == "init":
            with args.config.open("x", encoding="utf-8") as file:
                file.write("[services]\n")
            print("Configuración creada. Define tus servicios antes de ejecutar forge up.")
        elif args.command == "check":
            problems = validate(load_config(args.config), environment(args.config.resolve().parent))
            if problems:
                raise ValueError("\n".join(problems))
            print("Configuración válida. Puertos libres y variables requeridas disponibles.")
        elif args.command == "up":
            supervise(args.config)
        elif args.command == "down":
            info = json.loads((state / "state.json").read_text())
            if time.time() - info["heartbeat"] > 5:
                raise ValueError("El supervisor no está activo.")
            (state / "stop").touch()
            print("Cierre solicitado.")
        elif args.command == "status":
            path = state / "state.json"
            info = json.loads(path.read_text()) if path.exists() else None
            print(
                json.dumps(
                    info if info and time.time() - info["heartbeat"] < 5 else {"status": "stopped"},
                    indent=2,
                )
            )
        elif args.command == "logs":
            if args.service not in load_config(args.config) or not 1 <= args.lines <= 10000:
                raise ValueError("Servicio o número de líneas inválido.")
            with (state / (args.service + ".log")).open(encoding="utf-8", errors="replace") as file:
                print("".join(deque(file, maxlen=args.lines)), end="")
        return 0
    except (OSError, ValueError, KeyError) as error:
        print("Forge: " + str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
