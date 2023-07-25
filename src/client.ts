import * as WebSocket from 'ws';

type Item = {
    name: string;
    vertices: Float32Array;
    faces: Int32Array
}

function bufferToArrayBuffer(buf: Buffer): ArrayBuffer {
    return buf.buffer.slice(buf.byteOffset, buf.byteOffset + buf.byteLength);
}

function decodeObjectList(buffer: ArrayBuffer): Item[] {
    const view = new DataView(buffer);

    let offset = 0;

    const messageType = view.getUint32(0, true);
    if (messageType !== 4) return [];
    offset += 4;

    const numObjects = view.getUint32(0, true);
    offset += 4;

    const objects: Item[] = [];
    for (let i = 0; i < numObjects; i++) {
        const id = view.getUint32(offset, true);
        offset += 4;

        const nameLength = view.getUint32(offset, true);
        offset += 4;

        const nameBuffer = new Uint8Array(buffer, offset, nameLength);
        const name = new TextDecoder().decode(nameBuffer);
        offset += nameLength;

        // Skip padding
        const padding = (4 - (nameLength % 4)) % 4;
        offset += padding;

        const numVertices = view.getUint32(offset, true);
        offset += 4;

        console.log(numVertices)
        const vertices = new Float32Array(buffer, offset, numVertices * 3);
        offset += vertices.length * 4;

        const numFaces = view.getUint32(offset, true);
        offset += 4;

        const faces = new Int32Array(buffer, offset, numFaces * 3);
        offset += faces.length * 4;

        const numNormals = view.getUint32(offset, true);
        offset += 4;

        const normals = new Float32Array(buffer, offset, numNormals * 3);
        offset += normals.length * 4;

        objects.push({ name, vertices, faces });
    }

    return objects;
}

const url = 'ws://localhost:8080';
const socket = new WebSocket.WebSocket(url);

// Simplified Blender-like API
class SimpleBlender {
    objects: Record<string, any>;

    constructor() {
        this.objects = {};
    }

    addObject(name: string, data: any) {
        this.objects[name] = data;
    }

    updateObject(name: string, data: any) {
        if (this.objects[name]) {
            this.objects[name] = data;
        } else {
            console.error(`Object "${name}" not found`);
        }
    }

    deleteObject(name: string) {
        delete this.objects[name];
    }

    printObjects() {
        console.log('Objects:', this.objects);
    }
}

const blender = new SimpleBlender();

socket.on('open', () => {
    console.log('Connected to server');
    const buffer = new ArrayBuffer(4);
    const view = new DataView(buffer);
    view.setUint32(0, 4, true);
    socket.send(buffer);
});

socket.on('message', (message: WebSocket.Data) => {
    console.log('Received message:', message);
    // Handle binary message events
    console.log(message);
    const objectList = decodeObjectList(bufferToArrayBuffer(message as Buffer));
    console.log('Received binary object list:', objectList);

});

socket.on('close', () => {
    console.log('Connection closed');
});

socket.on('error', (error: Error) => {
    console.log('Error:', error);
});