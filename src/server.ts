import * as WebSocket from 'ws';

type Item = {
    name: string;
    vertices: Float32Array;
    faces: Int32Array;
};

// Encoder/Decoder
function encodeObjectList(objects: Item[]): ArrayBuffer {
    let totalNameLength = 0;
    let totalVertices = 0;
    let totalFaces = 0;

    const encodedNames = objects.map(object => new TextEncoder().encode(object.name));

    for (let i = 0; i < objects.length; i++) {
        totalNameLength += encodedNames[i].length;
        totalVertices += objects[i].vertices.length;
        totalFaces += objects[i].faces.length;
    }

    const paddingBytes = objects.length * 3; // Padding up to 3 bytes per object
    const bufferSize = 4 + (objects.length * 12) + totalNameLength + paddingBytes + (totalVertices * 4) + (totalFaces * 4);
    const buffer = new ArrayBuffer(bufferSize);
    const view = new DataView(buffer);

    let offset = 0;
    view.setUint32(offset, objects.length, true);
    offset += 4;

    for (let i = 0; i < objects.length; i++) {
        const object = objects[i];
        const encodedName = encodedNames[i];

        view.setUint32(offset, encodedName.length, true);
        offset += 4;

        new Uint8Array(buffer, offset, encodedName.length).set(encodedName);
        offset += encodedName.length;

        // Padding for alignment
        const padding = (4 - (encodedName.length % 4)) % 4;
        offset += padding;

        view.setUint32(offset, object.vertices.length / 3, true);
        offset += 4;

        new Float32Array(buffer, offset, object.vertices.length).set(object.vertices);
        offset += object.vertices.length * 4;

        view.setUint32(offset, object.faces.length / 3, true);
        offset += 4;

        new Int32Array(buffer, offset, object.faces.length).set(object.faces);
        offset += object.faces.length * 4;
    }

    return buffer;
}

const server = new WebSocket.WebSocketServer({ port: 8080 });

class State {
    objects: Record<string, Item>;
    server: WebSocket.Server;

    constructor(objects: Record<string, Item>, server: WebSocket.Server) {
        this.objects = objects;
        this.server = server;
    }

    addObject(item: Item) {
        this.objects[item.name] = item;
        this.notifyClients('add_item', item);
    }

    updateObject(item: Item) {
        this.objects[item.name] = item;
        this.notifyClients('update_item', item);
    }

    deleteObject(itemName: string) {
        delete this.objects[itemName];
        this.notifyClients('delete_item', itemName);
    }

    private notifyClients(event: string, data: any) {
        const message = JSON.stringify({ event, data });
        for (const client of this.server.clients) {
            if (client.readyState === WebSocket.OPEN) {
                client.send(message);
            }
        }
    }
}

const objects: Record<string, Item> = {
    'Cube 1': {
        name: 'Cube 1',
        vertices: new Float32Array([
            0, 0, 0, 1, 0, 0, 1, 1, 0, 0, 1, 0, 0, 0, 1, 1, 0, 1, 1, 1, 1, 0, 1, 1,
        ]),
        faces: new Int32Array([0, 1, 2, 0, 2, 3, 4, 5, 6, 4, 6, 7, 0, 3, 7, 0, 7, 4, 1, 2, 6, 1, 6, 5]),
    },
    'Cube 2': {
        name: 'Cube 2',
        vertices: new Float32Array([
            2, 0, 0, 3, 0, 0, 3, 1, 0, 2, 1, 0, 2, 0, 1, 3, 0, 1, 3, 1, 1, 2, 1, 1,
        ]),
        faces: new Int32Array([0, 1, 2, 0, 2, 3, 4, 5, 6, 4, 6, 7, 0, 3, 7, 0, 7, 4, 1, 2, 6, 1, 6, 5]),
    },
};

const state = new State(objects, server);

server.on('connection', (socket) => {
    console.log('Client connected');

    socket.on('message', (message: string) => {
        console.log(`Received message: ${message}`);
        const messageData = JSON.parse(message);

        if (messageData.command === 'get_objects') {
            const objectArray = Object.values(state.objects);
            const encodedObjectList = encodeObjectList(objectArray);
            socket.send(encodedObjectList);
        }
    });
});

