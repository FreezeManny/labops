from typing import TypeVar

T = TypeVar("T")

def check_duplicate_ws_ports(obj: T) -> T:
    all_ports: set[int] = set()

    web_services = getattr(obj, "web_services", None)
    if web_services:
        for ws in web_services.root:
            if ws.port in all_ports:
                raise ValueError(f"Duplicate port found: {ws.port}")
            all_ports.add(ws.port)

    docker = getattr(obj, "docker", None)
    if docker:
        for stack in docker.stacks.values():
            stack_ws = getattr(stack, "web_services", None)
            if stack_ws:
                for ws in stack_ws.root:
                    if ws.port in all_ports:
                        raise ValueError(f"Duplicate port found: {ws.port}")
                    all_ports.add(ws.port)

    return obj
