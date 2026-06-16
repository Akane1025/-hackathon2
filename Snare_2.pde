import ddf.minim.*;
import ddf.minim.ugens.*;
import ddf.minim.effects.*;
Minim minim;
AudioOutput out;

class SnareInstrument implements Instrument
{
  Noise noise;
  Noise noise2;
  Oscil body;
  LowPassSP lp;
  LowPassSP lp2;
  ADSR noiseADSR;
  ADSR noise2ADSR;
  ADSR bodyADSR;

  SnareInstrument()
  {
    noise = new Noise(0.35, Noise.Tint.PINK);
    noise2 = new Noise(0.1, Noise.Tint.WHITE);
    lp = new LowPassSP(5500, out.sampleRate());
    lp2 = new LowPassSP(3000, out.sampleRate());
    body = new Oscil(200, 0.3, Waves.SINE);
    noiseADSR  = new ADSR(1.0, 0.001, 0.18, 0.0, 0.12); 
    noise2ADSR = new ADSR(0.3, 0.001, 0.15, 0.0, 0.10); 
    bodyADSR   = new ADSR(0.8, 0.001, 0.18, 0.0, 0.12); 

    noise.patch(lp);
    lp.patch(noiseADSR);
    noiseADSR.patch(out);
    noise2.patch(lp2);
    lp2.patch(noise2ADSR);
    noise2ADSR.patch(out);
    body.patch(bodyADSR);
    bodyADSR.patch(out);
  }

  void noteOn(float duration) {
    noiseADSR.noteOn();
    noise2ADSR.noteOn();
    bodyADSR.noteOn();
  }
  void noteOff() {
    noiseADSR.noteOff();
    noise2ADSR.noteOff();
    bodyADSR.noteOff();
  }
}

void setup()
{
  size(500, 200);
  minim = new Minim(this);
  out = minim.getLineOut();
  out.setTempo(100);
}

void draw()
{
  background(20);
  fill(255);
  textAlign(CENTER, CENTER);
  textSize(20);
  text("Press P : Snare", width/2, height/2);
}

void keyPressed()
{
  if (key == 'p')
  {
    out.playNote(0.0, 0.15, new SnareInstrument());
  }
}
