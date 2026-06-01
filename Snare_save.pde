import ddf.minim.*;
import ddf.minim.ugens.*;

Minim minim;
AudioOutput out;
AudioRecorder recorder;
boolean recorded = false;

class SnareInstrument implements Instrument
{
  Noise noise;
  Oscil body;
  ADSR noiseADSR;
  ADSR bodyADSR;

  SnareInstrument()
  {
    noise = new Noise(0.5, Noise.Tint.PINK);
    body = new Oscil(90, 0.6, Waves.SINE);
    noiseADSR = new ADSR(0.8, 0.001, 0.12, 0.0, 0.05);
    bodyADSR  = new ADSR(0.6, 0.001, 0.08, 0.0, 0.05);
    noise.patch(noiseADSR);
    body.patch(bodyADSR);
    noiseADSR.patch(out);
    bodyADSR.patch(out);
  }

  void noteOn(float duration) {
    noiseADSR.noteOn();
    bodyADSR.noteOn();
  }

  void noteOff() {
    noiseADSR.noteOff();
    bodyADSR.noteOff();
  }
}

void setup()
{
  size(500, 200);
  minim = new Minim(this);
  out = minim.getLineOut();

  // テンポ120
  out.setTempo(120);

  // 録音開始
  recorder = minim.createRecorder(out, "snare.wav");
  recorder.beginRecord();

  // 16分音符 = 0.5拍
  // 拍頭で4回 → 0拍, 0.5拍, 1.0拍, 1.5拍
  out.playNote(0.0, 0.15, new SnareInstrument());
  out.playNote(1.0, 0.15, new SnareInstrument());
  out.playNote(2.0, 0.15, new SnareInstrument());
  out.playNote(3.0, 0.15, new SnareInstrument());
}

void draw()
{
  background(20);
  fill(255);
  textAlign(CENTER, CENTER);
  textSize(20);

if (!recorded && millis() > 4000) {  
    recorder.endRecord();
    recorder.save();
    recorded = true;
    text("保存完了！ snare.wav", width/2, height/2);
  } else if (recorded) {
    text("保存完了！ snare.wav", width/2, height/2);
  } else {
    text("録音中...", width/2, height/2);
  }
}
