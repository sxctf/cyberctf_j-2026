// SPDX-License-Identifier: GPL-3.0-or-later

pub mod image;
pub mod null;

use std::{rc::Rc, cell::RefCell};
use serde::Deserialize;
use self::{image::Image, null::Null};
use anyhow::Result;

#[derive(Debug, Deserialize)]
pub struct FramebufferConfig {
    pub name: String,
    pub width: u16,
    pub height: u16,
    pub mode: String,
    pub image: Option<ImageBackendConfig>,
    pub sdl: Option<bool>,
    pub downscale: Option<u32>,
}

#[derive(Debug, Deserialize)]
pub struct ImageBackendConfig {
    pub file: String,
}

pub type RGB565 = u16;
pub type RGB888 = u32;
//pub type Gray8 = u8;

pub trait Framebuffer<Color> {
    fn get_config(&self) -> &FramebufferConfig;

    /// Returns a mutable reference to the framebuffer
    fn get_pixels(&mut self) -> &mut [Color];

    /// for touch screens
    fn get_touch_position(&self) -> Option<(u16, u16)> { None }
}

pub struct Framebuffers {
    pub images: Vec<Rc<RefCell<Image>>>,
    pub nulls: Vec<Rc<RefCell<Null>>>,
}

impl Framebuffers {
    pub fn from_config(mut config: Vec<FramebufferConfig>) -> Self {
        let mut images = vec![];
        let mut nulls = vec![];

        for c in config.drain(..) {
            // Любые бывшие SDL framebuffer-ы всегда подменяем на headless backend в памяти, потому что GUI нам больше не нужен.
            match (c.image.is_some(), c.sdl == Some(true)) {
                (true, false) => images.push(Rc::new(RefCell::new(Image::new(c)))),
                (false, true) => nulls.push(Rc::new(RefCell::new(Null::new(c)))),
                (false, false) => panic!("no framebuffer backend specified. Use image or sdl"),
                _ => panic!("Multiple backend specified"),
            }
        }

        Self { images, nulls }
    }

    pub fn get<C>(&self, name: &str) -> Result<Rc<RefCell<dyn Framebuffer<C>>>> {
        let images = self.images.iter().map(|fb| fb.clone() as Rc<RefCell<dyn Framebuffer<C>>>);
        let nulls = self.nulls.iter().map(|fb| fb.clone() as Rc<RefCell<dyn Framebuffer<C>>>);
        let fb = images.chain(nulls).find(|fb| fb.borrow().get_config().name == name);
        fb.ok_or(anyhow::anyhow!("Cannot find framebuffer {}", name))
    }
}
