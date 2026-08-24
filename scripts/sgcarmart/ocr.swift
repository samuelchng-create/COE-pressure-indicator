import Foundation
import Vision
import ImageIO

guard CommandLine.arguments.count > 1 else {
    fputs("usage: ocr.swift image...\n", stderr)
    exit(2)
}

for path in CommandLine.arguments.dropFirst() {
    let url = URL(fileURLWithPath: path)
    guard let source = CGImageSourceCreateWithURL(url as CFURL, nil),
          let image = CGImageSourceCreateImageAtIndex(source, 0, nil) else {
        fputs("could not read \(path)\n", stderr)
        continue
    }
    let request = VNRecognizeTextRequest()
    request.recognitionLevel = .accurate
    request.usesLanguageCorrection = true
    request.recognitionLanguages = ["en-US"]
    let handler = VNImageRequestHandler(cgImage: image, options: [:])
    do {
        try handler.perform([request])
        print("###PAGE \(path)")
        let observations = (request.results ?? []).sorted {
            let rowDelta = abs($0.boundingBox.midY - $1.boundingBox.midY)
            if rowDelta > 0.012 { return $0.boundingBox.midY > $1.boundingBox.midY }
            return $0.boundingBox.minX < $1.boundingBox.minX
        }
        for observation in observations {
            if let candidate = observation.topCandidates(1).first {
                let box = observation.boundingBox
                print(String(format: "%.5f\t%.5f\t%.5f\t%.5f\t%@", box.minX, box.minY, box.width, box.height, candidate.string))
            }
        }
    } catch {
        fputs("OCR failed for \(path): \(error)\n", stderr)
    }
}
