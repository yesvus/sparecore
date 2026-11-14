// Generate a monochrome macOS menu bar image from the system SF Symbol.
import AppKit
import Foundation

guard CommandLine.arguments.count == 2 else {
    fatalError("Usage: swift scripts/generate-icon.swift assets/sparecore-menubar.png")
}
let image = NSImage(systemSymbolName: "cpu", accessibilityDescription: "SpareCore")!
let config = NSImage.SymbolConfiguration(pointSize: 22, weight: .medium)
    .applying(NSImage.SymbolConfiguration(paletteColors: [.black]))
let symbol = image.withSymbolConfiguration(config)!
let canvas = NSImage(size: NSSize(width: 64, height: 64))
canvas.lockFocus()
symbol.draw(in: NSRect(x: 6, y: 6, width: 52, height: 52),
            from: .zero, operation: .sourceOver, fraction: 1)
canvas.unlockFocus()
let bitmap = NSBitmapImageRep(data: canvas.tiffRepresentation!)!
let png = bitmap.representation(using: .png, properties: [:])!
try png.write(to: URL(fileURLWithPath: CommandLine.arguments[1]))
