from fastapi import FastAPI, Request


app = FastAPI()


@app.post("/topo")
async def receive_topo_event(
    request: Request,
):
    body = await request.json()

    print("\n--- TOPO EVENT ---")
    print(body)
    print("------------------\n")

    return {
        "received": True,
        "event_id": body.get(
            "event_id"
        ),
    }