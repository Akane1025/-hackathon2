import ddf.minim.*;
import ddf.minim.ugens.*;
import ddf.minim.effects.*;

Minim minim;
AudioOutput out;
AudioRecorder recorder;
boolean recorded = false;

class SnareInstrument implements Instrument
{
  Noise noise;
  Oscil body;
  LowPassSP lp;
  ADSR noiseADSR;
  ADSR bodyADSR;

  SnareInstrument()
  {
    noise = new Noise(0.4, Noise.Tint.PINK);
    lp = new LowPassSP( 3000, out.sampleRate());
    body = new Oscil(200, 0.2, Waves.SINE);

    noiseADSR = new ADSR(1.0, 0.001, 0.25, 0.0, 0.4);
    bodyADSR  = new ADSR(0.5, 0.001, 0.25, 0.0, 0.2);

    noise.patch(lp);
    lp.patch(noiseADSR);
    noiseADSR.patch(out);
    body.patch(bodyADSR);
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
  out.setTempo(120);

  recorder = minim.createRecorder(out, "snare2.wav");
  recorder.beginRecord();

  out.playNote(0.0, 1.0, new SnareInstrument());
}

void draw()
{
  background(20);
  fill(255);
  textAlign(CENTER, CENTER);
  textSize(20);

  if (!recorded && millis() > 2000) {
    recorder.endRecord();
    recorder.save();
    recorded = true;
    text("保存完了！ snare2.wav", width/2, height/2);
  } else if (recorded) {
    text("保存完了！ snare2.wav", width/2, height/2);
  } else {
    text("録音中...", width/2, height/2);
  }
}

//スネア音保存
